const KM_TO_MI = 0.621371
const M_TO_MI = 0.000621371
const KM_TO_YD = 1093.6132983377
const M_TO_YD = 1.0936132983377

export function isSwimDiscipline(value: string | null | undefined): boolean {
  if (!value) return false
  const normalized = value.trim().toLowerCase()
  return normalized.includes('swim') || normalized.includes('pool') || normalized.includes('wetsuit')
}

export function kilometersToMiles(km: number): number {
  return km * KM_TO_MI
}

export function kilometersToYards(km: number): number {
  return km * KM_TO_YD
}

export function metersToMiles(meters: number): number {
  return meters * M_TO_MI
}

export function metersToYards(meters: number): number {
  return meters * M_TO_YD
}

export function formatDistanceFromMeters(
  meters: number | null | undefined,
  discipline?: string | null,
): string {
  if (meters == null || meters <= 0) return '-'
  if (isSwimDiscipline(discipline)) {
    return `${Math.round(metersToYards(meters)).toLocaleString()} yd`
  }
  return `${metersToMiles(meters).toFixed(1)} mi`
}

export function formatDistanceFromKilometers(
  kilometers: number | null | undefined,
  discipline?: string | null,
): string {
  if (kilometers == null || kilometers <= 0) return '-'
  if (isSwimDiscipline(discipline)) {
    return `${Math.round(kilometersToYards(kilometers)).toLocaleString()} yd`
  }
  return `${kilometersToMiles(kilometers).toFixed(1)} mi`
}
