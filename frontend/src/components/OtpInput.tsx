import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react'

interface OtpInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  autoFocus?: boolean
  hasError?: boolean
}

export default function OtpInput({
  value,
  onChange,
  disabled = false,
  autoFocus = true,
  hasError = false,
}: OtpInputProps) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (autoFocus && inputRefs.current[0]) {
      inputRefs.current[0].focus()
    }
  }, [autoFocus])

  const digits = Array.from({ length: 6 }, (_, index) => value[index] || '')

  const handleChange = (index: number, char: string) => {
    const cleanChar = char.replace(/\D/g, '')
    if (!cleanChar && char !== '') return

    const currentChars = value.padEnd(6, ' ').split('').slice(0, 6)
    currentChars[index] = cleanChar ? cleanChar.slice(-1) : ' '
    const nextVal = currentChars.join('').trimEnd()
    onChange(nextVal)

    if (cleanChar && index < 5) {
      inputRefs.current[index + 1]?.focus()
    }
  }

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace') {
      if (!digits[index] && index > 0) {
        event.preventDefault()
        const currentChars = value.padEnd(6, ' ').split('').slice(0, 6)
        currentChars[index - 1] = ' '
        onChange(currentChars.join('').trimEnd())
        inputRefs.current[index - 1]?.focus()
      } else if (digits[index]) {
        event.preventDefault()
        const currentChars = value.padEnd(6, ' ').split('').slice(0, 6)
        currentChars[index] = ' '
        onChange(currentChars.join('').trimEnd())
      }
    } else if (event.key === 'ArrowLeft' && index > 0) {
      event.preventDefault()
      inputRefs.current[index - 1]?.focus()
    } else if (event.key === 'ArrowRight' && index < 5) {
      event.preventDefault()
      inputRefs.current[index + 1]?.focus()
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const pasted = event.clipboardData.getData('text')
    const digitsOnly = pasted.replace(/\D/g, '').slice(0, 6)
    if (!digitsOnly) return

    onChange(digitsOnly)
    const targetIndex = Math.min(digitsOnly.length, 5)
    inputRefs.current[targetIndex]?.focus()
  }

  return (
    <div
      className="otp-input-group"
      role="group"
      aria-label="6-digit verification code"
    >
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(el) => {
            inputRefs.current[index] = el
          }}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          pattern="[0-9]*"
          maxLength={1}
          value={digit.trim()}
          disabled={disabled}
          aria-label={`Digit ${index + 1} of 6`}
          className={`otp-digit-input ${hasError ? 'otp-digit-error' : ''}`}
          onChange={(e) => handleChange(index, e.target.value)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
        />
      ))}
    </div>
  )
}
