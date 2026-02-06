'use client'

import { useTasks, type Task } from '@/providers/tasks-provider'
import { cn } from '@/lib/utils'
import { CheckCircle2, Circle, Loader2, XCircle, ChevronDown, ChevronRight, Filter, Play, Pause } from 'lucide-react'
import { useState, useMemo } from 'react'

type FilterType = 'all' | 'pending' | 'in_progress' | 'completed'

function getStatusIcon(status: Task['status']) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
    case 'in_progress':
      return <Loader2 className="h-4 w-4 text-amber-500 animate-spin shrink-0" />
    case 'cancelled':
      return <XCircle className="h-4 w-4 text-red-500/60 shrink-0" />
    default:
      return <Circle className="h-4 w-4 text-zinc-500 shrink-0" />
  }
}

function TaskItem({ task, depth = 0 }: { task: Task; depth?: number }) {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasChildren = task.children && task.children.length > 0

  return (
    <div className="group">
      <div
        className={cn(
          'flex items-start gap-2 py-2 px-2 rounded-md hover:bg-[#1E1E1E] transition-colors cursor-default',
          depth > 0 && 'ml-4'
        )}
      >
        {/* Expand/collapse toggle */}
        {hasChildren ? (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-0.5 hover:bg-zinc-700 rounded shrink-0 mt-0.5"
          >
            {isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
            )}
          </button>
        ) : (
          <div className="w-4 shrink-0" />
        )}

        {/* Status icon */}
        <div className="mt-0.5">{getStatusIcon(task.status)}</div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div
            className={cn(
              'text-sm font-medium',
              task.status === 'completed' && 'text-zinc-500 line-through',
              task.status === 'cancelled' && 'text-zinc-600 line-through',
              task.status === 'in_progress' && 'text-amber-400',
              task.status === 'pending' && 'text-zinc-200'
            )}
          >
            {task.content}
          </div>
          {task.description && (
            <div className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{task.description}</div>
          )}
        </div>
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div className="border-l border-zinc-700/50 ml-[18px]">
          {task.children!.map(child => (
            <TaskItem key={child.id} task={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export function TaskListView() {
  const { tasks, lastUpdated } = useTasks()
  const [filter, setFilter] = useState<FilterType>('all')

  // Calculate task counts
  const counts = useMemo(() => {
    const count = (items: Task[]): { total: number; completed: number; inProgress: number; pending: number } => {
      let result = { total: 0, completed: 0, inProgress: 0, pending: 0 }
      for (const item of items) {
        result.total++
        if (item.status === 'completed') result.completed++
        else if (item.status === 'in_progress') result.inProgress++
        else if (item.status === 'pending') result.pending++
        if (item.children) {
          const childCounts = count(item.children)
          result.total += childCounts.total
          result.completed += childCounts.completed
          result.inProgress += childCounts.inProgress
          result.pending += childCounts.pending
        }
      }
      return result
    }
    return count(tasks)
  }, [tasks])

  // Filter tasks
  const filteredTasks = useMemo(() => {
    if (filter === 'all') return tasks
    const filterTree = (items: Task[]): Task[] => {
      return items
        .map(item => ({
          ...item,
          children: item.children ? filterTree(item.children) : undefined,
        }))
        .filter(item => item.status === filter || (item.children && item.children.length > 0))
    }
    return filterTree(tasks)
  }, [tasks, filter])

  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-zinc-500 px-4">
        <Circle className="h-12 w-12 mb-4 opacity-30" />
        <p className="text-sm font-medium">No tasks yet</p>
        <p className="text-xs text-center mt-1">The agent will create tasks when planning complex work</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header with counts and filter */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-zinc-400">
            {counts.completed}/{counts.total} completed
          </span>
          {counts.inProgress > 0 && (
            <span className="text-xs text-amber-500">• {counts.inProgress} active</span>
          )}
        </div>
        <select
          value={filter}
          onChange={e => setFilter(e.target.value as FilterType)}
          className="text-xs bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300"
        >
          <option value="all">All</option>
          <option value="pending">Pending</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto p-2">
        {filteredTasks.map(task => (
          <TaskItem key={task.id} task={task} />
        ))}
      </div>
    </div>
  )
}

