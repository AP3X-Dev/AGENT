import { NextRequest, NextResponse } from 'next/server'
import { readFile, writeFile, mkdir } from 'fs/promises'
import os from 'os'
import path from 'path'
import { existsSync } from 'fs'

/**
 * GET /api/skills?id=skill-id&path=/path/to/SKILL.md
 * Gets the full content of a skill by path
 */
export async function GET(request: NextRequest) {
  try {
    const skillPath = request.nextUrl.searchParams.get('path')
    
    if (!skillPath) {
      return NextResponse.json({ error: 'path parameter required' }, { status: 400 })
    }

    if (!existsSync(skillPath)) {
      return NextResponse.json({ error: 'Skill not found' }, { status: 404 })
    }

    const content = await readFile(skillPath, 'utf-8')
    return new NextResponse(content, {
      headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
    })
  } catch (error) {
    console.error('Error reading skill:', error)
    return NextResponse.json({ error: 'Failed to read skill' }, { status: 500 })
  }
}

/**
 * PUT /api/skills
 * Saves/updates a skill file
 * Body: { path: string, content: string }
 */
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json()
    const { path: skillPath, content } = body

    if (!skillPath || typeof content !== 'string') {
      return NextResponse.json(
        { error: 'path and content are required' },
        { status: 400 }
      )
    }

    // Ensure directory exists
    const dir = path.dirname(skillPath)
    if (!existsSync(dir)) {
      await mkdir(dir, { recursive: true })
    }

    await writeFile(skillPath, content, 'utf-8')

    return NextResponse.json({ success: true, path: skillPath })
  } catch (error) {
    console.error('Error saving skill:', error)
    return NextResponse.json({ error: 'Failed to save skill' }, { status: 500 })
  }
}

/**
 * POST /api/skills
 * Creates a new skill
 * Body: { id: string, name: string, description: string, ... }
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { id, name, description = '', mode = 'both', tags = [], tools = ['*'] } = body

    if (!id || !name) {
      return NextResponse.json(
        { error: 'id and name are required' },
        { status: 400 }
      )
    }

    // Validate ID format
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(id)) {
      return NextResponse.json(
        { error: 'ID must be lowercase alphanumeric with hyphens' },
        { status: 400 }
      )
    }

    const defaultBackendWin = 'C:\\Users\\Guerr\\Documents\\ag3nt'
    const ag3ntBackendPath =
      process.env.AG3NT_BACKEND_PATH ||
      process.env.NEXT_PUBLIC_AG3NT_BACKEND_PATH ||
      (existsSync(defaultBackendWin) ? defaultBackendWin : null)

    // Prefer workspace-local skills for AG3NT (repo_root/.ag3nt/skills).
    // Fallback to global user skills (~/.ag3nt/skills) if no backend path is configured.
    const workspaceRoot = ag3ntBackendPath && existsSync(ag3ntBackendPath) ? ag3ntBackendPath : null
    const baseDir = workspaceRoot
      ? path.join(workspaceRoot, '.ag3nt', 'skills')
      : path.join(os.homedir(), '.ag3nt', 'skills')

    const skillDir = path.join(baseDir, id)
    const skillPath = path.join(skillDir, 'SKILL.md')

    if (existsSync(skillPath)) {
      return NextResponse.json({ error: 'Skill already exists' }, { status: 409 })
    }

    // Create skill content
    const content = `---
id: ${id}
name: ${name}
description: ${description}
version: "1.0.0"
mode: ${mode}
tags: ${JSON.stringify(tags)}
tools: ${JSON.stringify(tools)}
inputs: ""
outputs: ""
safety: ""
triggers: []
---

## Purpose

Describe the purpose of this skill.

## When to Use

Describe when this skill should be used.

## Operating Procedure

1. Step one
2. Step two

## Tool Usage Rules

- Allowed tools and restrictions

## Output Format

Describe expected output format.

## Failure Modes and Recovery

1. **Error case**: Recovery steps.
`

    await mkdir(skillDir, { recursive: true })
    await writeFile(skillPath, content, 'utf-8')

    return NextResponse.json({
      success: true,
      path: skillPath,
      id,
    })
  } catch (error) {
    console.error('Error creating skill:', error)
    return NextResponse.json({ error: 'Failed to create skill' }, { status: 500 })
  }
}

