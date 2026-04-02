/**
 * Naive UI themeOverrides — 与 design-tokens.css 数值对齐，避免两套视觉语言。
 * 仅调整圆角、主色、边框与部分组件密度，不改变页面结构。
 */

const BRAND = {
  primary: '#2563eb',
  hover: '#1d4ed8',
  pressed: '#1e40af',
  suppl: '#3b82f6'
}

const BORDER = {
  light: '#dbe3f0',
  dark: '#24344f'
}

const RADIUS = {
  sm: '8px',
  md: '12px',
  lg: '16px'
}

/** @param {boolean} isDark */
export function getNaiveThemeOverrides(isDark) {
  const border = isDark ? BORDER.dark : BORDER.light

  return {
    common: {
      primaryColor: BRAND.primary,
      primaryColorHover: BRAND.hover,
      primaryColorPressed: BRAND.pressed,
      primaryColorSuppl: BRAND.suppl,
      borderRadius: RADIUS.md,
      borderRadiusSmall: RADIUS.sm,
      borderRadiusMedium: RADIUS.md,
      borderRadiusLarge: RADIUS.lg,
      borderColor: border,
      dividerColor: border,
      fontSize: '14px',
      fontSizeMini: '12px',
      fontSizeSmall: '13px',
      fontSizeMedium: '14px',
      fontSizeLarge: '15px',
      heightMedium: '40px'
    },
    Button: {
      borderRadiusTiny: RADIUS.sm,
      borderRadiusSmall: RADIUS.sm,
      borderRadiusMedium: RADIUS.md,
      borderRadiusLarge: RADIUS.lg,
      heightMedium: '40px',
      fontSizeMedium: '14px'
    },
    Input: {
      borderRadius: RADIUS.md,
      heightMedium: '40px',
      fontSizeMedium: '14px'
    },
    /* Select 内部选择框由 base.css 中 .n-base-selection 的 CSS 变量统一控制 */
    Card: {
      borderRadius: RADIUS.md,
      paddingMedium: '20px 22px',
      titleFontSize: '16px',
      titleFontWeight: '600'
    },
    Drawer: {
      borderRadius: RADIUS.lg
    },
    Modal: {
      borderRadius: RADIUS.lg
    },
    Dialog: {
      borderRadius: RADIUS.lg
    },
    Tag: {
      borderRadius: RADIUS.sm,
      heightMedium: '26px',
      fontSizeMedium: '12px'
    },
    Tabs: {
      tabBorderRadius: RADIUS.sm,
      tabFontWeight: '500',
      tabFontWeightActive: '600',
      tabGapMediumLine: '20px'
    },
    Spin: {
      opacitySpinning: 0.65
    },
    Popover: {
      borderRadius: RADIUS.md
    },
    Dropdown: {
      borderRadius: RADIUS.md,
      optionHeightMedium: '36px'
    },
    Checkbox: {
      borderRadius: '4px'
    },
    Radio: {
      buttonBorderRadius: RADIUS.sm
    },
    Switch: {
      railBorderRadius: '10px'
    },
    DataTable: {
      borderRadius: RADIUS.md,
      thPaddingMedium: '14px 16px',
      tdPaddingMedium: '14px 16px',
      thFontWeight: '600'
    },
    Empty: {
      textColor: isDark ? '#94a3b8' : '#64748b',
      iconColor: isDark ? '#475569' : '#94a3b8',
      fontSizeMedium: '14px'
    }
  }
}
