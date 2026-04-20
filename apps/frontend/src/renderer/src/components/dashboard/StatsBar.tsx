import { Calendar, Clock, CheckCircle, Stethoscope } from 'lucide-react'

interface StatsBarProps {
  todayCount: number
  pendingCount: number
  completedCount: number
  appointmentCount: number
}

interface StatCardProps {
  label: string
  value: number
  icon: React.ReactNode
  colorClass: string
}

function StatCard({ label, value, icon, colorClass }: StatCardProps): React.JSX.Element {
  return (
    <div className="flex items-center gap-4 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200/60">
      <div className={`flex h-12 w-12 items-center justify-center rounded-lg ${colorClass}`}>
        {icon}
      </div>
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className="text-2xl font-semibold text-slate-800">{value}</p>
      </div>
    </div>
  )
}

export function StatsBar({
  todayCount,
  pendingCount,
  completedCount,
  appointmentCount,
}: StatsBarProps): React.JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
      <StatCard
        label="Bugunun Randevulari"
        value={appointmentCount}
        icon={<Stethoscope className="h-6 w-6 text-purple-600" />}
        colorClass="bg-purple-50"
      />
      <StatCard
        label="Bugunun Gorusmeleri"
        value={todayCount}
        icon={<Calendar className="h-6 w-6 text-blue-600" />}
        colorClass="bg-blue-50"
      />
      <StatCard
        label="Bekleyen Inceleme"
        value={pendingCount}
        icon={<Clock className="h-6 w-6 text-amber-600" />}
        colorClass="bg-amber-50"
      />
      <StatCard
        label="Tamamlanan"
        value={completedCount}
        icon={<CheckCircle className="h-6 w-6 text-emerald-600" />}
        colorClass="bg-emerald-50"
      />
    </div>
  )
}
