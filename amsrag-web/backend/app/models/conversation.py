"""Conversation session and turn models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class ConversationSession(Base):
    """Persistent conversation container for a user and knowledge base."""

    __tablename__ = "conversation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, default="New conversation")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversation_sessions")
    knowledge_base = relationship(
        "KnowledgeBase",
        back_populates="conversation_sessions",
    )
    turns = relationship(
        "ConversationTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationTurn.turn_index",
    )

    def __repr__(self) -> str:
        return (
            f"<ConversationSession(id={self.id}, user_id={self.user_id}, "
            f"knowledge_base_id={self.knowledge_base_id})>"
        )


class ConversationTurn(Base):
    """One completed question-answer turn inside a conversation session."""

    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("conversation_sessions.id"),
        nullable=False,
        index=True,
    )
    turn_index = Column(Integer, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text)
    requested_mode = Column(String(20))
    mode = Column(String(20))
    response_time = Column(Float)
    token_count = Column(Integer)
    sources_json = Column(Text)
    memory_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ConversationSession", back_populates="turns")

    def __repr__(self) -> str:
        return (
            f"<ConversationTurn(id={self.id}, session_id={self.session_id}, "
            f"turn_index={self.turn_index})>"
        )
