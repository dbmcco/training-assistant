import type { RaceInfo } from '../../api/types'

interface RaceCountdownProps {
  races: RaceInfo[]
}

export default function RaceCountdown({ races }: RaceCountdownProps) {
  if (races.length === 0) return null

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-3">Upcoming Races</h3>

      <div className="space-y-3">
        {races.map((race) => {
          const raceDate = new Date(`${race.date}T00:00:00`)
          const dateStr = raceDate.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
          })

          return (
            <div
              key={`${race.name}-${race.date}`}
              className="flex items-center justify-between"
            >
              <div>
                <p className="text-sm font-medium text-gray-100">{race.name}</p>
                <p className="text-xs text-gray-500">{dateStr}</p>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-blue-400">
                  {race.weeks_out}
                </p>
                <p className="text-xs text-gray-500">weeks out</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
