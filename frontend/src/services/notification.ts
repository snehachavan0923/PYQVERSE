import Swal, { type SweetAlertIcon } from 'sweetalert2'

function themeOptions() {
  const dark = document.documentElement.dataset.theme === 'dark'
  return {
    background: dark ? '#132120' : '#ffffff',
    color: dark ? '#edf7f4' : '#17212b',
    confirmButtonColor: dark ? '#62c4a7' : '#176b5b',
    cancelButtonColor: dark ? '#29403d' : '#687684',
    customClass: {
      popup: 'pyq-swal-popup',
      title: 'pyq-swal-title',
      htmlContainer: 'pyq-swal-text',
      confirmButton: 'pyq-swal-confirm',
      cancelButton: 'pyq-swal-cancel',
      icon: 'pyq-swal-icon',
    },
  }
}

const base = () => themeOptions()

export const notification = {
  success(title: string, text?: string) {
    return Swal.fire({ ...base(), icon: 'success', title, text })
  },
  error(title: string, text?: string) {
    return Swal.fire({ ...base(), icon: 'error', title, text })
  },
  warning(title: string, text?: string) {
    return Swal.fire({ ...base(), icon: 'warning', title, text })
  },
  info(title: string, text?: string) {
    return Swal.fire({ ...base(), icon: 'info', title, text })
  },
  confirm(title: string, text: string, confirmText = 'Continue') {
    return Swal.fire({
      ...base(),
      icon: 'warning',
      title,
      text,
      showCancelButton: true,
      confirmButtonText: confirmText,
    })
  },
  toast(title: string, icon: SweetAlertIcon = 'success') {
    return Swal.fire({
      ...base(),
      toast: true,
      position: 'top-end',
      icon,
      title,
      showConfirmButton: false,
      timer: 2600,
      timerProgressBar: true,
    })
  },
}
