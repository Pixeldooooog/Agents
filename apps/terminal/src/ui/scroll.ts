export function nextScrollOffset({
  current,
  previousLines,
  nextLines,
  max
}: {
  current: number
  previousLines: number
  nextLines: number
  max: number
}): number {
  const delta = nextLines - previousLines
  const preserved = current > 0 && delta > 0 ? current + delta : current
  return clamp(preserved, 0, max)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
