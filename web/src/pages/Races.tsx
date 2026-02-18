import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchRaces,
  createRace,
  updateRace,
  deleteRace,
} from '../api/client'
import type { Race } from '../api/types'

const DISTANCE_TYPES = [
  { value: '5k', label: '5K' },
  { value: '10k', label: '10K' },
  { value: 'half_marathon', label: 'Half Marathon' },
  { value: 'marathon', label: 'Marathon' },
  { value: 'sprint_tri', label: 'Sprint Triathlon' },
  { value: 'olympic_tri', label: 'Olympic Triathlon' },
  { value: '70.3', label: '70.3' },
  { value: 'half_ironman', label: 'Half Ironman' },
  { value: '140.6', label: '140.6' },
  { value: 'ironman', label: 'Ironman' },
  { value: 'other', label: 'Other' },
] as const

function formatGoalTime(seconds: number | null): string {
  if (seconds == null) return '--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':')
}

function parseGoalTime(timeStr: string): number | null {
  if (!timeStr.trim()) return null
  const parts = timeStr.split(':').map(Number)
  if (parts.some(isNaN)) return null
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return null
}

function formatDistanceType(dt: string): string {
  const found = DISTANCE_TYPES.find((d) => d.value === dt)
  return found?.label ?? dt.replace(/_/g, ' ')
}

function getCountdown(dateStr: string): string {
  const raceDate = new Date(dateStr + 'T00:00:00')
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const diffMs = raceDate.getTime() - now.getTime()
  if (diffMs < 0) return 'Past'
  const totalDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))
  const weeks = Math.floor(totalDays / 7)
  const days = totalDays % 7
  const parts: string[] = []
  if (weeks > 0) parts.push(`${weeks}w`)
  if (days > 0 || weeks === 0) parts.push(`${days}d`)
  return parts.join(' ')
}

interface RaceFormData {
  name: string
  date: string
  distance_type: string
  goal_time_str: string
  notes: string
}

const emptyForm: RaceFormData = {
  name: '',
  date: '',
  distance_type: '5k',
  goal_time_str: '',
  notes: '',
}

function RaceForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  initial: RaceFormData
  onSubmit: (data: RaceFormData) => void
  onCancel: () => void
  submitLabel: string
}) {
  const [form, setForm] = useState<RaceFormData>(initial)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl bg-gray-900 border border-gray-800 p-4 space-y-4"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Race Name
          </label>
          <input
            type="text"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
            placeholder="e.g. Spring Half Marathon"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Date
          </label>
          <input
            type="date"
            required
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
            className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Distance Type
          </label>
          <select
            value={form.distance_type}
            onChange={(e) => setForm({ ...form, distance_type: e.target.value })}
            className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
          >
            {DISTANCE_TYPES.map((dt) => (
              <option key={dt.value} value={dt.value}>
                {dt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Goal Time (HH:MM:SS)
          </label>
          <input
            type="text"
            value={form.goal_time_str}
            onChange={(e) => setForm({ ...form, goal_time_str: e.target.value })}
            className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
            placeholder="e.g. 01:45:00"
          />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Notes
        </label>
        <textarea
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          rows={2}
          className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500 resize-none"
          placeholder="Optional notes..."
        />
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white transition-colors"
        >
          {submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm font-medium text-gray-300 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

function RaceRow({
  race,
  onEdit,
  onDelete,
}: {
  race: Race
  onEdit: (race: Race) => void
  onDelete: (id: string) => void
}) {
  const isPast = new Date(race.date + 'T00:00:00') < new Date()

  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        isPast
          ? 'border-gray-800/50 bg-gray-900/50 opacity-60'
          : 'border-gray-800 bg-gray-900'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <h3 className="text-base font-semibold text-gray-100 truncate">
              {race.name}
            </h3>
            <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-gray-800 text-gray-400">
              {formatDistanceType(race.distance_type)}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>
              {new Date(race.date + 'T00:00:00').toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </span>
            <span
              className={`font-semibold ${isPast ? 'text-gray-600' : 'text-blue-400'}`}
            >
              {getCountdown(race.date)}
            </span>
            {race.goal_time != null && (
              <span className="text-gray-400">
                Goal: {formatGoalTime(race.goal_time)}
              </span>
            )}
          </div>
          {race.notes && (
            <p className="text-xs text-gray-600 mt-2">{race.notes}</p>
          )}
        </div>
        <div className="flex items-center gap-1 ml-4 shrink-0">
          <button
            onClick={() => onEdit(race)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            aria-label="Edit race"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
            </svg>
          </button>
          <button
            onClick={() => onDelete(race.id)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors"
            aria-label="Delete race"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Races() {
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingRace, setEditingRace] = useState<Race | null>(null)

  const { data: races, isLoading } = useQuery({
    queryKey: ['races'],
    queryFn: fetchRaces,
  })

  const createMutation = useMutation({
    mutationFn: createRace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['races'] })
      setShowAddForm(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateRace>[1] }) =>
      updateRace(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['races'] })
      setEditingRace(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteRace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['races'] })
    },
  })

  const handleCreate = (form: RaceFormData) => {
    createMutation.mutate({
      name: form.name,
      date: form.date,
      distance_type: form.distance_type,
      goal_time: parseGoalTime(form.goal_time_str),
      notes: form.notes || null,
    })
  }

  const handleUpdate = (form: RaceFormData) => {
    if (!editingRace) return
    updateMutation.mutate({
      id: editingRace.id,
      data: {
        name: form.name,
        date: form.date,
        distance_type: form.distance_type,
        goal_time: parseGoalTime(form.goal_time_str),
        notes: form.notes || null,
      },
    })
  }

  const handleDelete = (id: string) => {
    deleteMutation.mutate(id)
  }

  const handleEdit = (race: Race) => {
    setEditingRace(race)
    setShowAddForm(false)
  }

  // Sort: upcoming races first (by date asc), then past races
  const sortedRaces = [...(races ?? [])].sort((a, b) => {
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    const aDate = new Date(a.date + 'T00:00:00')
    const bDate = new Date(b.date + 'T00:00:00')
    const aPast = aDate < now
    const bPast = bDate < now
    if (aPast !== bPast) return aPast ? 1 : -1
    return aDate.getTime() - bDate.getTime()
  })

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Races</h1>
        {!showAddForm && !editingRace && (
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z"
                clipRule="evenodd"
              />
            </svg>
            Add Race
          </button>
        )}
      </div>

      {/* Inline add form */}
      {showAddForm && (
        <RaceForm
          initial={emptyForm}
          onSubmit={handleCreate}
          onCancel={() => setShowAddForm(false)}
          submitLabel="Create Race"
        />
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="rounded-xl bg-gray-900 border border-gray-800 p-4 h-24"
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && sortedRaces.length === 0 && !showAddForm && (
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-8 text-center">
          <p className="text-gray-500 mb-2">No races scheduled yet</p>
          <button
            onClick={() => setShowAddForm(true)}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            Add your first race
          </button>
        </div>
      )}

      {/* Race list */}
      <div className="space-y-3">
        {sortedRaces.map((race) =>
          editingRace?.id === race.id ? (
            <RaceForm
              key={race.id}
              initial={{
                name: race.name,
                date: race.date,
                distance_type: race.distance_type,
                goal_time_str: race.goal_time != null ? formatGoalTime(race.goal_time) : '',
                notes: race.notes ?? '',
              }}
              onSubmit={handleUpdate}
              onCancel={() => setEditingRace(null)}
              submitLabel="Save Changes"
            />
          ) : (
            <RaceRow
              key={race.id}
              race={race}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ),
        )}
      </div>
    </div>
  )
}
