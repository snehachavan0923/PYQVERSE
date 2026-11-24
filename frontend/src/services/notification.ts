import Swal, { type SweetAlertResult } from 'sweetalert2'

type Theme = 'light' | 'dark'

export function currentTheme(): Theme {
  if (typeof document === 'undefined') return 'light'
  const attr = document.documentElement.dataset.theme
  if (attr === 'light' || attr === 'dark') return attr
  try {
    const stored = localStorage.getItem('pyqverse_theme')
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // localStorage can be unavailable in hardened environments.
  }
  return 'light'
}

function themeClasses(theme: Theme, danger = false) {
  const base = `pyq-swal pyq-swal-${theme}`
  return {
    container: `pyq-swal-container pyq-swal-container-${theme}`,
    popup: base,
    title: 'pyq-swal-title',
    html: 'pyq-swal-html',
    confirmButton: `pyq-swal-confirm${danger ? ' pyq-swal-confirm-danger' : ''}`,
    cancelButton: 'pyq-swal-cancel',
    actions: 'pyq-swal-actions',
    timerProgressBar: 'pyq-swal-timer',
  }
}

function baseOptions(theme: Theme) {
  return {
    background: 'transparent',
    color: 'inherit',
    iconColor: theme === 'dark' ? '#62c4a7' : '#176b5b',
    buttonsStyling: false,
    reverseButtons: true,
    focusCancel: false,
    customClass: themeClasses(theme),
  }
}

function dialog(theme: Theme, danger: boolean) {
  return {
    ...baseOptions(theme),
    customClass: danger ? themeClasses(theme, true) : themeClasses(theme),
  }
}

const toastMixin = Swal.mixin({
  toast: true,
  position: 'top-end',
  showConfirmButton: false,
  timer: 2800,
  timerProgressBar: true,
  didOpen: (toast) => {
    toast.addEventListener('mouseenter', Swal.stopTimer)
    toast.addEventListener('mouseleave', Swal.resumeTimer)
  },
})

export function toast(
  type: 'success' | 'error' | 'warning' | 'info',
  title: string,
): Promise<SweetAlertResult> {
  const theme = currentTheme()
  return toastMixin.fire({
    ...baseOptions(theme),
    icon: type,
    title,
    customClass: {
      ...themeClasses(theme),
      popup: `pyq-swal pyq-swal-${theme} pyq-swal-toast`,
    },
  })
}

export function success(title: string, text?: string): Promise<SweetAlertResult> {
  return Swal.fire({
    ...dialog(currentTheme(), false),
    icon: 'success',
    title,
    text,
  })
}

export function error(title: string, text?: string): Promise<SweetAlertResult> {
  return Swal.fire({
    ...dialog(currentTheme(), true),
    icon: 'error',
    title,
    text,
    confirmButtonText: 'Dismiss',
  })
}

export async function retryError(title: string, text?: string): Promise<boolean> {
  const result = await Swal.fire({
    ...dialog(currentTheme(), true),
    icon: 'error',
    title,
    text,
    showCancelButton: true,
    confirmButtonText: 'Retry',
    cancelButtonText: 'Dismiss',
  })
  return result.isConfirmed === true
}

export function warning(title: string, text?: string): Promise<SweetAlertResult> {
  return Swal.fire({
    ...dialog(currentTheme(), false),
    icon: 'warning',
    title,
    text,
  })
}

export function info(title: string, text?: string): Promise<SweetAlertResult> {
  return Swal.fire({
    ...dialog(currentTheme(), false),
    icon: 'info',
    title,
    text,
  })
}

export interface ConfirmOptions {
  title: string
  text?: string
  confirmText?: string
  cancelText?: string
  destructive?: boolean
}

export async function confirm({
  title,
  text,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  destructive = false,
}: ConfirmOptions): Promise<boolean> {
  const result = await Swal.fire({
    ...dialog(currentTheme(), destructive),
    icon: destructive ? 'warning' : 'question',
    title,
    text,
    showCancelButton: true,
    confirmButtonText: confirmText,
    cancelButtonText: cancelText,
  })
  return result.isConfirmed === true
}

const notifications = {
  success,
  error,
  retryError,
  warning,
  info,
  confirm,
  toast,
  currentTheme,
}
export default notifications
