import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, List, Union

from neo4j import AsyncGraphDatabase

from ..._utils import logger
from ...answer_generation.prompts import GRAPH_FIELD_SEP
from ...base import BaseGraphStorage, SingleCommunitySchema

neo4j_lock = asyncio.Lock()


def make_path_idable(path):
    return path.replace(".", "_").replace("/", "__").replace("-", "_").replace(":", "_").replace("\\", "__")


def make_label_idable(label: str) -> str:
    normalized = make_path_idable((label or "UNKNOWN").strip('"').strip())
    return (normalized or "UNKNOWN").upper()


@dataclass
class Neo4jStorage(BaseGraphStorage):
    def __post_init__(self):
        self.neo4j_url = self.global_config["addon_params"].get("neo4j_url", None)
        self.neo4j_auth = self.global_config["addon_params"].get("neo4j_auth", None)
        self.namespace = (
            f"{make_path_idable(self.global_config['working_dir'])}__{self.namespace}"
        )
        logger.info(f"Using the label {self.namespace} for Neo4j as identifier")
        if self.neo4j_url is None or self.neo4j_auth is None:
            raise ValueError("Missing neo4j_url or neo4j_auth in addon_params")
        self.async_driver = self._make_driver()
        self._session_semaphore = asyncio.Semaphore(8)
        self._retry_attempts = 2

    def _make_driver(self):
        return AsyncGraphDatabase.driver(
            self.neo4j_url,
            auth=self.neo4j_auth,
            max_connection_pool_size=12,
            connection_acquisition_timeout=30,
            # Retire connections after 10 minutes to prevent stale TCP connections
            # from being used after the server-side resets them (common on cloud Neo4j).
            max_connection_lifetime=600,
        )

    async def _run_with_session(
        self,
        callback: Callable,
        *,
        readonly: bool = False,
        retries: int | None = None,
    ):
        attempt_limit = (self._retry_attempts if retries is None else retries) + 1
        last_error = None

        for attempt in range(1, attempt_limit + 1):
            try:
                async with self._session_semaphore:
                    async with self.async_driver.session() as session:
                        return await callback(session)
            except Exception as exc:
                last_error = exc
                if attempt >= attempt_limit:
                    raise
                logger.warning(
                    f"Neo4j {'read' if readonly else 'write'} operation failed for namespace "
                    f"{self.namespace} on attempt {attempt}/{attempt_limit}: {exc}. Retrying..."
                )
                # If this looks like a stale-connection error, recreate the driver
                # before the next attempt so we don't keep hammering dead connections.
                if self._is_stale_connection_error(exc):
                    await self._recreate_driver()
                await asyncio.sleep(0.2 * attempt)

        raise last_error

    def _is_stale_connection_error(self, exc: Exception) -> bool:
        from neo4j.exceptions import ServiceUnavailable, SessionExpired
        exc_str = str(exc).lower()
        return (
            isinstance(exc, (ServiceUnavailable, SessionExpired))
            or "routing" in exc_str
            or "connectionreset" in exc_str
            or "connection lost" in exc_str
            or "connection reset" in exc_str
        )

    async def _recreate_driver(self) -> None:
        try:
            await self.async_driver.close()
        except Exception:
            pass
        self.async_driver = self._make_driver()
        logger.info(f"Recreated Neo4j driver for namespace {self.namespace}")

    async def _init_workspace(self):
        try:
            await self.async_driver.verify_authentication()
            await self.async_driver.verify_connectivity()
        except Exception as exc:
            if self._is_stale_connection_error(exc):
                logger.warning(
                    f"Stale Neo4j driver detected for namespace {self.namespace} "
                    f"({type(exc).__name__}: {exc}). Recreating driver and retrying..."
                )
                await self._recreate_driver()
                # Retry once with a fresh driver
                await self.async_driver.verify_authentication()
                await self.async_driver.verify_connectivity()
            else:
                raise

    async def index_start_callback(self):
        logger.info("Init Neo4j workspace")
        await self._init_workspace()

        namespace = self.namespace

        async def _setup_indexes(session):
            from neo4j.exceptions import ClientError

            # In Neo4j 5.x, DROP INDEX requires an explicit index NAME – the
            # pattern-based syntax "DROP INDEX IF EXISTS FOR (n:...) ON (n.prop)"
            # is NOT valid Cypher. We therefore query SHOW INDEXES to discover
            # any plain (non-constraint-backing) index on (n.id) for this label
            # and drop it by name before creating the UNIQUE CONSTRAINT.
            async def _drop_plain_id_indexes() -> int:
                dropped = 0
                # Some Neo4j environments are picky about combining SHOW commands
                # with WHERE/RETURN clauses. Fetch all indexes and filter client-side.
                result = await session.run("SHOW INDEXES")
                records = await result.data()

                for record in records:
                    owning_constraint = record.get("owningConstraint")
                    if owning_constraint is not None:
                        continue

                    props = record.get("properties") or []
                    if list(props) != ["id"]:
                        continue

                    labels_or_types = record.get("labelsOrTypes") or []
                    if namespace not in list(labels_or_types):
                        continue

                    idx_name = record.get("name")
                    if not idx_name:
                        continue

                    logger.info(
                        f"Dropping conflicting plain index '{idx_name}' "
                        f"on label {namespace}(id) before creating UNIQUE CONSTRAINT"
                    )
                    try:
                        drop_cur = await session.run(f"DROP INDEX `{idx_name}` IF EXISTS")
                        await drop_cur.consume()
                        dropped += 1
                    except ClientError as drop_exc:
                        logger.warning(
                            f"Failed to drop index '{idx_name}' before constraint creation: {drop_exc}. "
                            "It may have been dropped already or removed concurrently."
                        )
                return dropped

            try:
                await _drop_plain_id_indexes()
            except Exception as e:
                logger.warning(f"Could not pre-clean conflicting indexes: {e}")

            # Create UNIQUE constraint first. If it fails due to an existing plain index,
            # do a targeted cleanup and retry once (covers race/partial runs).
            constraint_stmt = (
                f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:`{namespace}`) REQUIRE n.id IS UNIQUE"
            )
            try:
                cursor = await session.run(constraint_stmt)
                await cursor.consume()
            except ClientError as e:
                code = getattr(e, "code", "") or ""
                if code == "Neo.ClientError.Schema.IndexAlreadyExists":
                    logger.warning(
                        f"Constraint creation blocked by existing plain index; "
                        f"attempting cleanup + retry. Error: {e}"
                    )
                    try:
                        dropped = await _drop_plain_id_indexes()
                        logger.info(f"Dropped {dropped} conflicting index(es); retrying constraint creation")
                    except Exception as cleanup_exc:
                        logger.warning(f"Cleanup failed; will re-raise original error. Cleanup error: {cleanup_exc}")
                        raise
                    cursor2 = await session.run(constraint_stmt)
                    await cursor2.consume()
                else:
                    raise

            statements = [
                f"CREATE INDEX IF NOT EXISTS FOR (n:`{namespace}`) ON (n.entity_type)",
                f"CREATE INDEX IF NOT EXISTS FOR (n:`{namespace}`) ON (n.communityIds)",
                f"CREATE INDEX IF NOT EXISTS FOR (n:`{namespace}`) ON (n.source_id)",
            ]
            for statement in statements:
                cursor = await session.run(statement)
                await cursor.consume()
            logger.info("Neo4j indexes created successfully")

        try:
            await self._run_with_session(_setup_indexes, retries=1)
        except Exception as exc:
            logger.error(f"Failed to create indexes: {exc}")
            raise

    async def has_node(self, node_id: str) -> bool:
        async def _check(session):
            result = await session.run(
                f"MATCH (n:`{self.namespace}`) WHERE n.id = $node_id RETURN COUNT(n) > 0 AS exists",
                node_id=node_id,
            )
            record = await result.single()
            return record["exists"] if record else False

        return await self._run_with_session(_check, readonly=True)

    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        async def _check(session):
            result = await session.run(
                f"""
                MATCH (s:`{self.namespace}`)
                WHERE s.id = $source_id
                MATCH (t:`{self.namespace}`)
                WHERE t.id = $target_id
                RETURN EXISTS((s)-[]->(t)) AS exists
                """,
                source_id=source_node_id,
                target_id=target_node_id,
            )
            record = await result.single()
            return record["exists"] if record else False

        return await self._run_with_session(_check, readonly=True)

    async def node_degree(self, node_id: str) -> int:
        results = await self.node_degrees_batch([node_id])
        return results[0] if results else 0

    async def node_degrees_batch(self, node_ids: List[str]) -> List[int]:
        if not node_ids:
            return []

        result_dict = {node_id: 0 for node_id in node_ids}

        async def _load(session):
            result = await session.run(
                f"""
                UNWIND $node_ids AS node_id
                MATCH (n:`{self.namespace}`)
                WHERE n.id = node_id
                OPTIONAL MATCH (n)-[]-(m:`{self.namespace}`)
                RETURN node_id, COUNT(m) AS degree
                """,
                node_ids=node_ids,
            )
            async for record in result:
                result_dict[record["node_id"]] = record["degree"]

        await self._run_with_session(_load, readonly=True)
        return [result_dict[node_id] for node_id in node_ids]

    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        results = await self.edge_degrees_batch([(src_id, tgt_id)])
        return results[0] if results else 0

    async def edge_degrees_batch(self, edge_pairs: list[tuple[str, str]]) -> list[int]:
        if not edge_pairs:
            return []

        result_dict = {tuple(edge_pair): 0 for edge_pair in edge_pairs}
        edges_params = [{"src_id": src, "tgt_id": tgt} for src, tgt in edge_pairs]

        async def _load(session):
            result = await session.run(
                f"""
                UNWIND $edges AS edge

                MATCH (s:`{self.namespace}`)
                WHERE s.id = edge.src_id
                WITH edge, s
                OPTIONAL MATCH (s)-[]-(n1:`{self.namespace}`)
                WITH edge, COUNT(n1) AS src_degree

                MATCH (t:`{self.namespace}`)
                WHERE t.id = edge.tgt_id
                WITH edge, src_degree, t
                OPTIONAL MATCH (t)-[]-(n2:`{self.namespace}`)
                WITH edge.src_id AS src_id, edge.tgt_id AS tgt_id, src_degree, COUNT(n2) AS tgt_degree

                RETURN src_id, tgt_id, src_degree + tgt_degree AS degree
                """,
                edges=edges_params,
            )

            async for record in result:
                edge_pair = (record["src_id"], record["tgt_id"])
                result_dict[edge_pair] = record["degree"]

        try:
            await self._run_with_session(_load, readonly=True)
            return [result_dict[tuple(edge_pair)] for edge_pair in edge_pairs]
        except Exception as exc:
            logger.error(f"Error in batch edge degree calculation: {exc}")
            return [0] * len(edge_pairs)

    async def get_node(self, node_id: str) -> Union[dict, None]:
        result = await self.get_nodes_batch([node_id])
        return result.get(node_id)

    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, Union[dict, None]]:
        if not node_ids:
            return {}

        result_dict = {node_id: None for node_id in node_ids}

        async def _load(session):
            result = await session.run(
                f"""
                UNWIND $node_ids AS node_id
                MATCH (n:`{self.namespace}`)
                WHERE n.id = node_id
                RETURN node_id, properties(n) AS node_data
                """,
                node_ids=node_ids,
            )

            async for record in result:
                current_node_id = record["node_id"]
                raw_node_data = record["node_data"]
                if raw_node_data:
                    raw_node_data["clusters"] = json.dumps(
                        [
                            {"level": index, "cluster": cluster_id}
                            for index, cluster_id in enumerate(raw_node_data.get("communityIds", []))
                        ]
                    )
                    result_dict[current_node_id] = raw_node_data

        try:
            await self._run_with_session(_load, readonly=True)
            return result_dict
        except Exception as exc:
            logger.error(f"Error in batch node retrieval: {exc}")
            raise

    async def get_edge(self, source_node_id: str, target_node_id: str) -> Union[dict, None]:
        results = await self.get_edges_batch([(source_node_id, target_node_id)])
        return results[0] if results else None

    async def get_edges_batch(self, edge_pairs: list[tuple[str, str]]) -> list[Union[dict, None]]:
        if not edge_pairs:
            return []

        result_dict = {tuple(edge_pair): None for edge_pair in edge_pairs}
        edges_params = [{"source_id": src, "target_id": tgt} for src, tgt in edge_pairs]

        async def _load(session):
            result = await session.run(
                f"""
                UNWIND $edges AS edge
                MATCH (s:`{self.namespace}`)-[r]->(t:`{self.namespace}`)
                WHERE s.id = edge.source_id AND t.id = edge.target_id
                RETURN edge.source_id AS source_id, edge.target_id AS target_id, properties(r) AS edge_data
                """,
                edges=edges_params,
            )

            async for record in result:
                edge_pair = (record["source_id"], record["target_id"])
                result_dict[edge_pair] = record["edge_data"]

        try:
            await self._run_with_session(_load, readonly=True)
            return [result_dict[tuple(edge_pair)] for edge_pair in edge_pairs]
        except Exception as exc:
            logger.error(f"Error in batch edge retrieval: {exc}")
            return [None] * len(edge_pairs)

    async def get_node_edges(self, source_node_id: str) -> list[tuple[str, str]]:
        results = await self.get_nodes_edges_batch([source_node_id])
        return results[0] if results else []

    async def get_nodes_edges_batch(self, node_ids: list[str]) -> list[list[tuple[str, str]]]:
        if not node_ids:
            return []

        result_dict = {node_id: [] for node_id in node_ids}

        async def _load(session):
            result = await session.run(
                f"""
                UNWIND $node_ids AS node_id
                MATCH (s:`{self.namespace}`)-[r]->(t:`{self.namespace}`)
                WHERE s.id = node_id
                RETURN s.id AS source_id, t.id AS target_id
                """,
                node_ids=node_ids,
            )

            async for record in result:
                source_id = record["source_id"]
                target_id = record["target_id"]
                if source_id in result_dict:
                    result_dict[source_id].append((source_id, target_id))

        try:
            await self._run_with_session(_load, readonly=True)
            return [result_dict[node_id] for node_id in node_ids]
        except Exception as exc:
            logger.error(f"Error in batch node edges retrieval: {exc}")
            return [[] for _ in node_ids]

    async def upsert_node(self, node_id: str, node_data: dict[str, str]):
        await self.upsert_nodes_batch([(node_id, node_data)])

    async def upsert_nodes_batch(self, nodes_data: list[tuple[str, dict[str, str]]]):
        if not nodes_data:
            return []

        nodes_by_type = {}
        for node_id, node_data in nodes_data:
            node_type = make_label_idable(node_data.get("entity_type", "UNKNOWN"))
            nodes_by_type.setdefault(node_type, []).append((node_id, node_data))

        async def _upsert(session):
            for node_type, type_nodes in nodes_by_type.items():
                params = [{"id": node_id, "data": node_data} for node_id, node_data in type_nodes]
                cursor = await session.run(
                    f"""
                    UNWIND $nodes AS node
                    MERGE (n:`{self.namespace}` {{id: node.id}})
                    SET n += node.data
                    SET n:`{node_type}`
                    """,
                    nodes=params,
                )
                await cursor.consume()

        await self._run_with_session(_upsert)

    async def upsert_edge(self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]):
        await self.upsert_edges_batch([(source_node_id, target_node_id, edge_data)])

    async def upsert_edges_batch(self, edges_data: list[tuple[str, str, dict[str, str]]]):
        if not edges_data:
            return

        edges_params = []
        for source_id, target_id, edge_data in edges_data:
            edge_data_copy = edge_data.copy()
            edge_data_copy.setdefault("weight", 0.0)
            edges_params.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_data": edge_data_copy,
                }
            )

        async def _upsert(session):
            cursor = await session.run(
                f"""
                UNWIND $edges AS edge
                MATCH (s:`{self.namespace}`)
                WHERE s.id = edge.source_id
                WITH edge, s
                MATCH (t:`{self.namespace}`)
                WHERE t.id = edge.target_id
                MERGE (s)-[r:RELATED]->(t)
                SET r += edge.edge_data
                """,
                edges=edges_params,
            )
            await cursor.consume()

        await self._run_with_session(_upsert)

    async def clustering(self, algorithm: str):
        if algorithm != "leiden":
            raise ValueError(
                f"Clustering algorithm {algorithm} not supported in Neo4j implementation"
            )

        random_seed = self.global_config["graph_cluster_seed"]
        max_level = self.global_config["max_graph_cluster_size"]

        async def _cluster(session):
            from neo4j.exceptions import ClientError

            graph_name = f"graph_{self.namespace}"
            projected = False
            try:
                projection_cursor = await session.run(
                    f"""
                    CALL gds.graph.project(
                        '{graph_name}',
                        ['{self.namespace}'],
                        {{
                            RELATED: {{
                                orientation: 'UNDIRECTED',
                                properties: ['weight']
                            }}
                        }}
                    )
                    """
                )
                await projection_cursor.consume()
                projected = True

                result = await session.run(
                    f"""
                    CALL gds.leiden.write(
                        '{graph_name}',
                        {{
                            writeProperty: 'communityIds',
                            includeIntermediateCommunities: True,
                            relationshipWeightProperty: 'weight',
                            maxLevels: {max_level},
                            tolerance: 0.0001,
                            gamma: 1.0,
                            theta: 0.01,
                            randomSeed: {random_seed}
                        }}
                    )
                    YIELD communityCount, modularities
                    """
                )
                record = await result.single()
                logger.info(
                    "Performed graph clustering with {} communities and modularities {}",
                    record["communityCount"],
                    record["modularities"],
                )
            except ClientError as e:
                code = getattr(e, "code", "") or ""
                if code == "Neo.ClientError.Procedure.ProcedureNotFound":
                    # Neo4j Graph Data Science (GDS) is not installed/enabled.
                    # Clustering is an enhancement step; skipping it keeps insert/delete flows usable.
                    logger.warning(
                        f"Neo4j GDS procedures not available (e.g. gds.graph.project). "
                        f"Skipping clustering for namespace {self.namespace}. Error: {e}"
                    )
                    return
                raise
            finally:
                if not projected:
                    return
                try:
                    drop_cursor = await session.run(f"CALL gds.graph.drop('{graph_name}')")
                    await drop_cursor.consume()
                except Exception as drop_exc:
                    # Best-effort cleanup: projection may already be gone if the session died mid-run.
                    msg = str(drop_exc)
                    if "does not exist" in msg or "NoSuchElementException" in msg:
                        return
                    logger.warning(f"Failed to drop projected GDS graph '{graph_name}': {drop_exc}")

        await self._run_with_session(_cluster)

    async def community_schema(self) -> dict[str, SingleCommunitySchema]:
        results = defaultdict(
            lambda: dict(
                level=None,
                title=None,
                edges=set(),
                nodes=set(),
                chunk_ids=set(),
                occurrence=0.0,
                sub_communities=[],
            )
        )

        async def _load(session):
            result = await session.run(
                f"""
                MATCH (n:`{self.namespace}`)
                WITH n, n.communityIds AS communityIds, [(n)-[]-(m:`{self.namespace}`) | m.id] AS connected_nodes
                RETURN n.id AS node_id, n.source_id AS source_id,
                       communityIds AS cluster_key,
                       connected_nodes
                """
            )

            max_num_ids = 0
            async for record in result:
                cluster_keys = record["cluster_key"] or []
                source_id = record["source_id"] or ""
                connected_nodes = record["connected_nodes"] or []
                for index, cluster_id in enumerate(cluster_keys):
                    node_id = str(record["node_id"])
                    cluster_key = str(cluster_id)
                    results[cluster_key]["level"] = index
                    results[cluster_key]["title"] = f"Cluster {cluster_key}"
                    results[cluster_key]["nodes"].add(node_id)
                    results[cluster_key]["edges"].update(
                        [
                            tuple(sorted([node_id, str(connected)]))
                            for connected in connected_nodes
                            if connected != node_id
                        ]
                    )
                    if source_id:
                        results[cluster_key]["chunk_ids"].update(source_id.split(GRAPH_FIELD_SEP))
                    max_num_ids = max(max_num_ids, len(results[cluster_key]["chunk_ids"]))

            max_num_ids = max(max_num_ids, 1)
            for cluster in results.values():
                cluster["edges"] = [list(edge) for edge in cluster["edges"]]
                cluster["nodes"] = list(cluster["nodes"])
                cluster["chunk_ids"] = list(cluster["chunk_ids"])
                cluster["occurrence"] = len(cluster["chunk_ids"]) / max_num_ids

            for cluster in results.values():
                cluster["sub_communities"] = [
                    sub_key
                    for sub_key, sub_cluster in results.items()
                    if sub_cluster["level"] > cluster["level"]
                    and set(sub_cluster["nodes"]).issubset(set(cluster["nodes"]))
                ]

        await self._run_with_session(_load, readonly=True)
        return dict(results)

    async def index_done_callback(self):
        # The backend caches initialized RAG services per knowledge base.
        # Closing the Neo4j driver after each insert/query cycle leaves the
        # cached service holding a defunct driver for subsequent operations.
        return None

    async def _debug_delete_all_node_edges(self):
        async def _delete(session):
            rel_cursor = await session.run(f"MATCH (n:`{self.namespace}`)-[r]-() DELETE r")
            await rel_cursor.consume()
            node_cursor = await session.run(f"MATCH (n:`{self.namespace}`) DELETE n")
            await node_cursor.consume()
            logger.info(
                f"All nodes and edges in namespace '{self.namespace}' have been deleted."
            )

        try:
            await self._run_with_session(_delete, retries=1)
        except Exception as exc:
            logger.error(f"Error deleting nodes and edges: {exc}")
            raise

    async def close(self):
        await self.async_driver.close()
