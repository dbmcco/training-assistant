import { useQuery } from '@tanstack/react-query'
import {
  fetchAthleteProfile,
  fetchAthleteBiometrics,
  fetchAthleteRecords,
  fetchAthleteGear,
} from '../api/client'
import type {
  AthleteBiometrics,
  PersonalRecord,
  GearItem,
} from '../api/types'

function BiometricCard({
  label,
  value,
  unit,
}: {
  label: string
  value: string | number | null
  unit?: string
}) {
  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-4">
      <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-100">
        {value != null ? (
          <>
            {value}
            {unit && <span className="text-sm font-normal text-gray-500 ml-1">{unit}</span>}
          </>
        ) : (
          <span className="text-gray-700">--</span>
        )}
      </p>
    </div>
  )
}

function BiometricsSection({
  biometrics,
  isLoading,
}: {
  biometrics: AthleteBiometrics | undefined
  isLoading: boolean
}) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-pulse">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="rounded-xl bg-gray-900 border border-gray-800 p-4 h-20" />
        ))}
      </div>
    )
  }

  if (!biometrics) {
    return (
      <div className="rounded-xl bg-gray-900 border border-gray-800 p-6 text-center">
        <p className="text-gray-500">No biometric data available</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <BiometricCard label="Weight" value={biometrics.weight} unit="kg" />
      <BiometricCard label="Body Fat" value={biometrics.body_fat} unit="%" />
      <BiometricCard label="Muscle Mass" value={biometrics.muscle_mass} unit="kg" />
      <BiometricCard label="BMI" value={biometrics.bmi} />
      <BiometricCard label="Fitness Age" value={biometrics.fitness_age} unit="yrs" />
      <BiometricCard label="LT Heart Rate" value={biometrics.lt_hr} unit="bpm" />
      <BiometricCard label="LT Pace" value={biometrics.lt_pace} unit="/km" />
      <BiometricCard label="Cycling FTP" value={biometrics.cycling_ftp} unit="W" />
    </div>
  )
}

function RecordsSection({
  records,
  isLoading,
}: {
  records: PersonalRecord[] | undefined
  isLoading: boolean
}) {
  if (isLoading) {
    return (
      <div className="rounded-xl bg-gray-900 border border-gray-800 overflow-hidden animate-pulse">
        <div className="h-48" />
      </div>
    )
  }

  if (!records || records.length === 0) {
    return (
      <div className="rounded-xl bg-gray-900 border border-gray-800 p-6 text-center">
        <p className="text-gray-500">No personal records yet</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Activity
            </th>
            <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Record Type
            </th>
            <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Value
            </th>
            <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Date
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {records.map((record) => (
            <tr key={record.id} className="hover:bg-gray-800/30 transition-colors">
              <td className="px-4 py-3 text-gray-300 capitalize">
                {record.activity_type.replace(/_/g, ' ')}
              </td>
              <td className="px-4 py-3 text-gray-400 capitalize">
                {record.record_type.replace(/_/g, ' ')}
              </td>
              <td className="px-4 py-3 text-right text-gray-100 font-medium">
                {record.value}{' '}
                <span className="text-gray-500 text-xs">{record.unit}</span>
              </td>
              <td className="px-4 py-3 text-right text-gray-500">
                {record.date
                  ? new Date(record.date + 'T00:00:00').toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })
                  : '--'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const gearTypeIcons: Record<string, string> = {
  shoes: '\u{1F45F}',
  bike: '\u{1F6B2}',
  wetsuit: '\u{1F3CA}',
  helmet: '\u{26D1}',
  watch: '\u{231A}',
}

function GearSection({
  gear,
  isLoading,
}: {
  gear: GearItem[] | undefined
  isLoading: boolean
}) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 animate-pulse">
        {[1, 2].map((i) => (
          <div key={i} className="rounded-xl bg-gray-900 border border-gray-800 p-4 h-24" />
        ))}
      </div>
    )
  }

  if (!gear || gear.length === 0) {
    return (
      <div className="rounded-xl bg-gray-900 border border-gray-800 p-6 text-center">
        <p className="text-gray-500">No gear tracked yet</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {gear.map((item) => {
        const icon = gearTypeIcons[item.type.toLowerCase()] ?? '\u{1F3CB}'
        return (
          <div
            key={item.id}
            className="rounded-xl bg-gray-900 border border-gray-800 p-4 hover:border-gray-700 transition-colors"
          >
            <div className="flex items-start gap-3">
              <span className="text-2xl">{icon}</span>
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-semibold text-gray-100 truncate">
                  {item.name}
                </h4>
                <p className="text-xs text-gray-500">
                  {[item.brand, item.model].filter(Boolean).join(' ') || item.type}
                </p>
                <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                  {item.total_distance != null && (
                    <span>
                      <span className="text-gray-300 font-medium">
                        {item.total_distance.toLocaleString()}
                      </span>{' '}
                      km
                    </span>
                  )}
                  {item.total_activities != null && (
                    <span>
                      <span className="text-gray-300 font-medium">
                        {item.total_activities}
                      </span>{' '}
                      activities
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function Profile() {
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['athleteProfile'],
    queryFn: fetchAthleteProfile,
  })

  const { data: biometrics, isLoading: biometricsLoading } = useQuery({
    queryKey: ['athleteBiometrics'],
    queryFn: fetchAthleteBiometrics,
  })

  const { data: records, isLoading: recordsLoading } = useQuery({
    queryKey: ['athleteRecords'],
    queryFn: fetchAthleteRecords,
  })

  const { data: gear, isLoading: gearLoading } = useQuery({
    queryKey: ['athleteGear'],
    queryFn: fetchAthleteGear,
  })

  return (
    <div className="p-6 space-y-8">
      {/* Header */}
      <div>
        {profileLoading ? (
          <div className="animate-pulse">
            <div className="h-8 bg-gray-800 rounded w-48 mb-2" />
            <div className="h-4 bg-gray-800 rounded w-32" />
          </div>
        ) : profile ? (
          <>
            <h1 className="text-2xl font-bold">{profile.name}</h1>
            <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
              {profile.email && <span>{profile.email}</span>}
              {profile.age != null && <span>Age {profile.age}</span>}
              {profile.gender && (
                <span className="capitalize">{profile.gender}</span>
              )}
            </div>
          </>
        ) : (
          <h1 className="text-2xl font-bold">Profile</h1>
        )}
      </div>

      {/* Biometrics */}
      <section>
        <h2 className="text-lg font-semibold text-gray-200 mb-3">Biometrics</h2>
        <BiometricsSection biometrics={biometrics} isLoading={biometricsLoading} />
      </section>

      {/* Personal Records */}
      <section>
        <h2 className="text-lg font-semibold text-gray-200 mb-3">
          Personal Records
        </h2>
        <RecordsSection records={records} isLoading={recordsLoading} />
      </section>

      {/* Gear */}
      <section>
        <h2 className="text-lg font-semibold text-gray-200 mb-3">Gear</h2>
        <GearSection gear={gear} isLoading={gearLoading} />
      </section>
    </div>
  )
}
