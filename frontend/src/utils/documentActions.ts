export function isPdfFile(fileType: string | null | undefined): boolean {
  return (fileType ?? '').trim().toLowerCase() === 'pdf'
}

export function openPreviewWindow(): Window | null {
  if (typeof window === 'undefined') return null
  const win = window.open('', '_blank')
  if (win) {
    try {
      win.opener = null
    } catch {
      // Some browsers refuse to mutate the opener; the tab is still safe to use.
    }
  }
  return win
}

export function loadPreview(win: Window | null, url: string): boolean {
  if (!win) return false
  win.location.href = url
  return true
}

export function closePreviewWindow(win: Window | null): void {
  if (!win) return
  try {
    win.close()
  } catch {
    // Closing a window that the browser already dismissed is harmless.
  }
}

export function triggerDownload(url: string): void {
  if (typeof document === 'undefined') return
  const link = document.createElement('a')
  link.href = url
  link.rel = 'noopener noreferrer'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
}
