import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import { Button } from '../components/ui'
import { API_BASE_URL } from '../lib/api'

export default function CompanyActionPlansPage() {
  const { user } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState(null)

  useEffect(() => {
    fetchActionPlans()
  }, [user])

  const fetchActionPlans = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/company/action-plans`, {
        headers: {
          'X-User-Role': user?.role || 'company',
          'X-User-Email': user?.email || '',
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch action plans: ${response.status}`)
      }

      const actionPlansData = await response.json()
      setData(actionPlansData)
      setError(null)
    } catch (err) {
      console.error('Error fetching action plans:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Action Plans" subtitle="Loading...">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Action Plans" subtitle="Error loading data">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">Make sure the backend server is running</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Action Plans" subtitle="No data available">
          <p className="text-gray-600">Unable to load action plans.</p>
        </SectionCard>
      </div>
    )
  }

  const totalActions = data.active_actions.length + data.completed_actions.length + data.overdue_actions.length

  return (
    <div className="page-grid">
      {/* Header Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard title="Active" value={data.active_actions.length} color="blue" />
        <StatCard title="Completed" value={data.completed_actions.length} color="green" />
        <StatCard title="Overdue" value={data.overdue_actions.length} color="red" />
        <StatCard title="Total" value={totalActions} color="indigo" />
      </div>

      {/* Add New Action Button */}
      <div className="col-span-1 lg:col-span-full mb-4">
        <Button
          onClick={() => setShowAddForm(!showAddForm)}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 ui-text-strong transition-colors"
        >
          {showAddForm ? '✕ Cancel' : '+ Add New Action Plan'}
        </Button>
      </div>

      {/* Add Form */}
      {showAddForm && (
        <SectionCard title="Create New Action Plan" subtitle="Add a new ESG improvement initiative">
          <ActionPlanForm
            onSuccess={() => {
              setShowAddForm(false)
              fetchActionPlans()
            }}
            user={user}
            onCancel={() => setShowAddForm(false)}
          />
        </SectionCard>
      )}

      {/* Active Action Plans */}
      {data.active_actions.length > 0 && (
        <SectionCard
          title="Active Initiatives"
          subtitle={`${data.active_actions.length} action plan(s) in progress`}
        >
          <div className="space-y-4">
            {data.active_actions.map((action) => (
              <ActionPlanCard
                key={action.id}
                action={action}
                status="active"
                onUpdate={fetchActionPlans}
                user={user}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Overdue Actions */}
      {data.overdue_actions.length > 0 && (
        <SectionCard
          title="Overdue Actions"
          subtitle={`${data.overdue_actions.length} action plan(s) past target date`}
        >
          <div className="space-y-4">
            {data.overdue_actions.map((action) => (
              <ActionPlanCard
                key={action.id}
                action={action}
                status="overdue"
                onUpdate={fetchActionPlans}
                user={user}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Completed Actions */}
      {data.completed_actions.length > 0 && (
        <SectionCard
          title="Completed Initiatives"
          subtitle={`${data.completed_actions.length} action plan(s) completed`}
        >
          <div className="space-y-4">
            {data.completed_actions.map((action) => (
              <ActionPlanCard
                key={action.id}
                action={action}
                status="completed"
                onUpdate={fetchActionPlans}
                user={user}
              />
            ))}
          </div>
        </SectionCard>
      )}

      {/* Empty State */}
      {totalActions === 0 && (
        <SectionCard title="No Action Plans Yet" subtitle="Start adding ESG improvement initiatives">
          <div className="text-center py-8">
            <p className="text-gray-600 mb-4">You haven't created any action plans yet.</p>
            <Button
              onClick={() => setShowAddForm(true)}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 ui-text-strong transition-colors"
            >
              Create First Action Plan
            </Button>
          </div>
        </SectionCard>
      )}
    </div>
  )
}

function StatCard({ title, value, color }) {
  const colors = {
    blue: 'bg-blue-50 border-blue-200 text-blue-600',
    green: 'bg-green-50 border-green-200 text-green-600',
    red: 'bg-red-50 border-red-200 text-red-600',
    indigo: 'bg-indigo-50 border-indigo-200 text-indigo-600',
  }

  return (
    <div className={`p-4 rounded-lg border ${colors[color]}`}>
      <p className="text-sm ui-text-strong opacity-75">{title}</p>
      <p className="ui-text-display mt-1">{value}</p>
    </div>
  )
}

function ActionPlanCard({ action, status, onUpdate, user }) {
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this action plan?')) return

    try {
      setDeleting(true)
      const response = await fetch(`${API_BASE_URL}/company/action-plans/${action.id}`, {
        method: 'DELETE',
        headers: {
          'X-User-Role': user?.role || 'company',
          'X-User-Email': user?.email || '',
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error('Failed to delete action plan')
      }

      onUpdate()
    } catch (err) {
      alert('Error deleting action plan: ' + err.message)
    } finally {
      setDeleting(false)
    }
  }

  const statusColors = {
    active: 'border-l-4 border-blue-500 bg-blue-50',
    overdue: 'border-l-4 border-red-500 bg-red-50',
    completed: 'border-l-4 border-green-500 bg-green-50',
  }

  const statusIcons = {
    active: '⚡',
    overdue: '🚨',
    completed: '✅',
  }

  return (
    <div className={`p-4 rounded-lg ${statusColors[status]}`}>
      {editing ? (
        <ActionPlanForm
          action={action}
          onSuccess={() => {
            setEditing(false)
            onUpdate()
          }}
          user={user}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <div className="flex justify-between items-start mb-3">
            <div className="flex-1">
              <h3 className="ui-text-strong ui-text-display text-gray-800">
                {statusIcons[status]} {action.title}
              </h3>
              {action.description && (
                <p className="text-sm text-gray-700 mt-1">{action.description}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 text-sm">
            <div>
              <p className="text-gray-600">Owner</p>
              <p className="ui-text-strong text-gray-800">{action.owner}</p>
            </div>
            <div>
              <p className="text-gray-600">Target Date</p>
              <p className="ui-text-strong text-gray-800">{action.target_date}</p>
            </div>
            <div>
              <p className="text-gray-600">Status</p>
              <p className="ui-text-strong text-gray-800">{action.status}</p>
            </div>
          </div>

          {action.linked_metric && (
            <div className="mb-4 p-2 bg-gray-100 rounded text-sm">
              <span className="text-gray-700">Linked to: <span className="ui-text-strong">{action.linked_metric}</span></span>
            </div>
          )}

          <div className="flex gap-2">
            <Button
              onClick={() => setEditing(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm ui-text-strong transition-colors"
            >
              Edit
            </Button>
            <Button
              onClick={handleDelete}
              disabled={deleting}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm ui-text-strong transition-colors disabled:bg-gray-400"
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

function ActionPlanForm({ action = null, onSuccess, user, onCancel }) {
  const [formData, setFormData] = useState({
    title: action?.title || '',
    description: action?.description || '',
    owner: action?.owner || '',
    target_date: action?.target_date || '',
    linked_metric: action?.linked_metric || '',
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()

    try {
      setSaving(true)
      const url = action
        ? `${API_BASE_URL}/company/action-plans/${action.id}`
        : `${API_BASE_URL}/company/action-plans`

      const response = await fetch(url, {
        method: action ? 'PUT' : 'POST',
        headers: {
          'X-User-Role': user?.role || 'company',
          'X-User-Email': user?.email || '',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: formData.title,
          description: formData.description,
          owner: formData.owner,
          target_date: formData.target_date,
          linked_metric: formData.linked_metric,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to save action plan')
      }

      onSuccess()
    } catch (err) {
      alert('Error saving action plan: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm ui-text-strong text-gray-700 mb-1">Action Title *</label>
        <input
          type="text"
          value={formData.title}
          onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          placeholder="e.g., Reduce emissions by 15%"
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div>
        <label className="block text-sm ui-text-strong text-gray-700 mb-1">Description</label>
        <textarea
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder="Describe the action plan..."
          rows="3"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm ui-text-strong text-gray-700 mb-1">Responsible Owner *</label>
          <input
            type="text"
            value={formData.owner}
            onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
            placeholder="Name or role"
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm ui-text-strong text-gray-700 mb-1">Target Date *</label>
          <input
            type="date"
            value={formData.target_date}
            onChange={(e) => setFormData({ ...formData, target_date: e.target.value })}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm ui-text-strong text-gray-700 mb-1">Linked Metric/Area</label>
        <input
          type="text"
          value={formData.linked_metric}
          onChange={(e) => setFormData({ ...formData, linked_metric: e.target.value })}
          placeholder="e.g., Scope 1 Emissions, Female Representation"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="flex gap-3 pt-4">
        <Button
          type="submit"
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 ui-text-strong transition-colors"
        >
          {saving ? 'Saving...' : action ? 'Update' : 'Create'}
        </Button>
        <Button
          type="button"
          onClick={onCancel}
          className="px-6 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400 ui-text-strong transition-colors"
        >
          Cancel
        </Button>
      </div>
    </form>
  )
}


