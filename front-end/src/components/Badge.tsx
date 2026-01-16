import React from 'react'

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

type Props = {
  variant?: Variant
  children: React.ReactNode
}

export default function Badge({ variant = 'neutral', children }: Props) {
  return (
    <span className={`badge badge--${variant}`.trim()}>
      {children}
    </span>
  )
}
