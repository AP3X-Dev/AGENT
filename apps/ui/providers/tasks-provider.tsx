'use client'

import { createContext, useContext, useReducer, useCallback, type ReactNode } from 'react'

// Task types matching the agent's write_todos format
export interface Task {
  id: string
  content: string
  description?: string
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled'
  parentId?: string | null
  children?: Task[]
}

interface TasksState {
  tasks: Task[]
  isVisible: boolean  // Whether tasks panel is showing
  lastUpdated: number | null
}

interface TasksContextType extends TasksState {
  setTasks: (tasks: Task[]) => void
  updateTask: (id: string, updates: Partial<Task>) => void
  toggleTasksView: () => void
  setTasksVisible: (visible: boolean) => void
  clearTasks: () => void
}

type TasksAction =
  | { type: 'SET_TASKS'; payload: Task[] }
  | { type: 'UPDATE_TASK'; payload: { id: string; updates: Partial<Task> } }
  | { type: 'TOGGLE_VISIBILITY' }
  | { type: 'SET_VISIBILITY'; payload: boolean }
  | { type: 'CLEAR_TASKS' }

const initialState: TasksState = {
  tasks: [],
  isVisible: false,
  lastUpdated: null,
}

function tasksReducer(state: TasksState, action: TasksAction): TasksState {
  switch (action.type) {
    case 'SET_TASKS':
      return { ...state, tasks: action.payload, lastUpdated: Date.now() }
    case 'UPDATE_TASK':
      return {
        ...state,
        tasks: updateTaskInTree(state.tasks, action.payload.id, action.payload.updates),
        lastUpdated: Date.now(),
      }
    case 'TOGGLE_VISIBILITY':
      return { ...state, isVisible: !state.isVisible }
    case 'SET_VISIBILITY':
      return { ...state, isVisible: action.payload }
    case 'CLEAR_TASKS':
      return { ...state, tasks: [], lastUpdated: null }
    default:
      return state
  }
}

// Helper to update a task in a nested tree
function updateTaskInTree(tasks: Task[], id: string, updates: Partial<Task>): Task[] {
  return tasks.map(task => {
    if (task.id === id) {
      return { ...task, ...updates }
    }
    if (task.children && task.children.length > 0) {
      return { ...task, children: updateTaskInTree(task.children, id, updates) }
    }
    return task
  })
}

// Build hierarchical tree from flat tasks with parentId
function buildTaskTree(flatTasks: Task[]): Task[] {
  const taskMap = new Map<string, Task>()
  const rootTasks: Task[] = []

  // First pass: create all tasks in map
  for (const task of flatTasks) {
    taskMap.set(task.id, { ...task, children: [] })
  }

  // Second pass: build tree structure
  for (const task of flatTasks) {
    const taskWithChildren = taskMap.get(task.id)!
    if (task.parentId && taskMap.has(task.parentId)) {
      const parent = taskMap.get(task.parentId)!
      parent.children = parent.children || []
      parent.children.push(taskWithChildren)
    } else {
      rootTasks.push(taskWithChildren)
    }
  }

  return rootTasks
}

const TasksContext = createContext<TasksContextType | undefined>(undefined)

export function TasksProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(tasksReducer, initialState)

  const setTasks = useCallback((tasks: Task[]) => {
    // Build hierarchical tree from flat tasks with parentId
    const treeifiedTasks = buildTaskTree(tasks)
    dispatch({ type: 'SET_TASKS', payload: treeifiedTasks })
  }, [])

  const updateTask = useCallback((id: string, updates: Partial<Task>) => {
    dispatch({ type: 'UPDATE_TASK', payload: { id, updates } })
  }, [])

  const toggleTasksView = useCallback(() => {
    dispatch({ type: 'TOGGLE_VISIBILITY' })
  }, [])

  const setTasksVisible = useCallback((visible: boolean) => {
    dispatch({ type: 'SET_VISIBILITY', payload: visible })
  }, [])

  const clearTasks = useCallback(() => {
    dispatch({ type: 'CLEAR_TASKS' })
  }, [])

  const contextValue: TasksContextType = {
    ...state,
    setTasks,
    updateTask,
    toggleTasksView,
    setTasksVisible,
    clearTasks,
  }

  return <TasksContext.Provider value={contextValue}>{children}</TasksContext.Provider>
}

export function useTasks() {
  const context = useContext(TasksContext)
  if (context === undefined) {
    throw new Error('useTasks must be used within a TasksProvider')
  }
  return context
}

