import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET() {
  try {
    // Path to the configs directory
    const configsPath = path.join(process.cwd(), '..', 'massgen', 'configs')
    
    // Check if directory exists
    if (!fs.existsSync(configsPath)) {
      return NextResponse.json({ error: 'Configs directory not found' }, { status: 404 })
    }
    
    // Read directory contents
    const files = fs.readdirSync(configsPath)
    
    // Filter for .yaml files only and exclude .md files
    const configFiles = files.filter(file => 
      file.endsWith('.yaml') || file.endsWith('.yml')
    )
    
    // Read content of each config file
    const configs: Record<string, string> = {}
    
    for (const file of configFiles) {
      try {
        const filePath = path.join(configsPath, file)
        const content = fs.readFileSync(filePath, 'utf8')
        configs[file] = content
      } catch (error) {
        console.error(`Error reading file ${file}:`, error)
        // Continue with other files even if one fails
      }
    }
    
    return NextResponse.json({ configs })
  } catch (error) {
    console.error('Error loading config files:', error)
    return NextResponse.json({ error: 'Failed to load config files' }, { status: 500 })
  }
}