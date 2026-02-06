import { NextRequest, NextResponse } from 'next/server'
import { writeFile, mkdir } from 'fs/promises'
import { join } from 'path'
import { existsSync } from 'fs'
import { isStandaloneUi } from '@/lib/standalone'

export const runtime = 'nodejs'
export const maxDuration = 120 // 2 minutes for image generation

const OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'
const DEFAULT_IMAGE_MODEL = 'google/gemini-3-pro-image-preview'

const ASPECT_RATIOS: Record<string, string> = {
  '1:1': '1024×1024',
  '2:3': '832×1248',
  '3:2': '1248×832',
  '3:4': '864×1184',
  '4:3': '1184×864',
  '4:5': '896×1152',
  '5:4': '1152×896',
  '9:16': '768×1344',
  '16:9': '1344×768',
  '21:9': '1536×672',
}

interface GenerateImageRequest {
  prompt: string
  aspectRatio?: string
  imageSize?: string
}

function extractImageFromResponse(data: any): { success: boolean; imageData: string | null; error: string | null } {
  const choices = data?.choices || []
  if (!choices.length) {
    return { success: false, imageData: null, error: 'No response from model' }
  }

  const message = choices[0]?.message || {}
  
  // Check for images array
  const images = message.images || []
  if (images.length > 0) {
    const img = images[0]
    const imageUrl = img?.imageUrl?.url || img?.image_url?.url || img?.url || (typeof img === 'string' ? img : null)
    if (imageUrl) {
      if (imageUrl.startsWith('data:')) {
        const [, b64Data] = imageUrl.split(',')
        return { success: true, imageData: b64Data, error: null }
      }
      return { success: true, imageData: imageUrl, error: null }
    }
  }

  // Check content array for image parts
  const content = message.content
  if (Array.isArray(content)) {
    for (const part of content) {
      if (typeof part === 'object') {
        const partType = part.type || ''
        
        if (partType === 'image_url') {
          const url = part.image_url?.url || part.url || ''
          if (url) {
            if (url.startsWith('data:')) {
              const [, b64Data] = url.split(',')
              return { success: true, imageData: b64Data, error: null }
            }
            return { success: true, imageData: url, error: null }
          }
        }
        
        if (partType === 'inline_data' || part.inline_data) {
          const inline = part.inline_data || part
          if (inline?.data) {
            return { success: true, imageData: inline.data, error: null }
          }
        }
        
        if (partType === 'image') {
          const imgData = part.source?.data || part.data
          if (imgData) {
            return { success: true, imageData: imgData, error: null }
          }
        }
      }
    }
  }

  // If content is a string, model may have declined
  if (typeof content === 'string') {
    if (['cannot', "can't", 'unable', 'sorry', 'inappropriate'].some(w => content.toLowerCase().includes(w))) {
      return { success: false, imageData: null, error: `Model declined: ${content.slice(0, 500)}` }
    }
    return { success: false, imageData: null, error: `No image generated. Model said: ${content.slice(0, 300)}` }
  }

  return { success: false, imageData: null, error: 'No image in response' }
}

export async function POST(request: NextRequest) {
  try {
    const body: GenerateImageRequest = await request.json()
    const { prompt, aspectRatio = '1:1', imageSize = '1K' } = body

    if (!prompt) {
      return NextResponse.json({ error: 'Prompt is required' }, { status: 400 })
    }

    const apiKey = process.env.OPENROUTER_API_KEY
    const model = process.env.OPENROUTER_IMAGE_MODEL || DEFAULT_IMAGE_MODEL

    if (isStandaloneUi()) {
      return NextResponse.json(
        { error: 'Image generation is unavailable in standalone UI mode' },
        { status: 400 }
      )
    }

    if (!apiKey) {
      return NextResponse.json(
        { error: 'OPENROUTER_API_KEY is required for image generation' },
        { status: 500 }
      )
    }

    if (!ASPECT_RATIOS[aspectRatio]) {
      return NextResponse.json({ 
        error: `Invalid aspect ratio. Options: ${Object.keys(ASPECT_RATIOS).join(', ')}` 
      }, { status: 400 })
    }

    // Call OpenRouter with image generation config
    const response = await fetch(OPENROUTER_API_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://github.com/ap3x-dev/ag3nt',
        'X-Title': 'AP3X-UI',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: prompt }],
        modalities: ['image', 'text'],
        image_config: {
          aspect_ratio: aspectRatio,
          image_size: imageSize,
        },
      }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      console.error('OpenRouter Image API error:', errorData)
      return NextResponse.json({ error: `OpenRouter API error: ${response.statusText}` }, { status: response.status })
    }

    const data = await response.json()
    const result = extractImageFromResponse(data)

    if (!result.success) {
      return NextResponse.json({ error: result.error }, { status: 500 })
    }

    // Save image to workspace
    const workspaceDir = join(process.cwd(), 'workspace')
    if (!existsSync(workspaceDir)) {
      await mkdir(workspaceDir, { recursive: true })
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    const filename = `image_${timestamp}.png`
    const filePath = join(workspaceDir, filename)

    // Decode and save
    const imageBuffer = Buffer.from(result.imageData!, 'base64')
    await writeFile(filePath, imageBuffer)

    return NextResponse.json({
      success: true,
      imagePath: `/workspace/${filename}`,
      imageData: result.imageData,
      message: `Image generated and saved to: workspace/${filename}`,
    })
  } catch (error: any) {
    console.error('Image generation error:', error)
    return NextResponse.json({ error: error.message || 'Failed to generate image' }, { status: 500 })
  }
}
