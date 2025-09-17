# MassGen UI

A web-based interface for the MassGen multi-agent coordination system, built with Next.js 14, React Mosaic, and Zustand.

## Features

- **Multi-Panel Dashboard**: Support for 40+ different panel types
- **Vertical Tiling Layout**: Terminal-style panel stacking with drag & drop resizing
- **Real-time Coordination**: Live agent status updates and content streaming
- **Command Center**: Central panel management with toggle controls
- **Demo Simulation**: Interactive demo showing multi-agent collaboration

## Quick Start

```bash
# Install dependencies
yarn install

# Run development server
yarn dev

# Open http://localhost:3000
```

## Demo Usage

1. **Command Center**: Use the top bar to toggle panels on/off
2. **Demo Simulation**: Click "Run Demo Simulation" to see multi-agent coordination
3. **Panel Management**: Drag panel borders to resize, toggle panels from command center
4. **Real-time Updates**: Watch agents stream content and coordinate in real-time

## Architecture

### Tech Stack
- **Next.js 14**: React framework with App Router
- **React Mosaic**: Tiling window manager for panel layout
- **Zustand**: Lightweight state management
- **TypeScript**: Type safety
- **Tailwind CSS**: Styling

### Key Components

- `usePanelStore`: Global state management (Zustand store)
- `CommandCenter`: Top bar for panel management and status
- `PanelComponent`: Individual panel rendering with auto-scroll
- `DemoSimulation`: Automated demo of agent coordination

### Panel Types

- Agent panels (Claude, Gemini, GPT-5)
- Coordination Hub
- Voting Results  
- Final Presentation
- Tool Usage
- System Logs
- Configuration

## Future Integration

This UI is designed to integrate with the MassGen Python backend via:
- WebSocket connections for real-time streaming
- REST API for panel management and configuration
- Server-sent events for live agent coordination updates

## Development

```bash
# Type checking
yarn build

# Linting
yarn lint

# Start production server
yarn start
```

The UI follows the same terminal-style coordination display as the current MassGen Python interface, but with enhanced interactivity and visual management.

---

## Original Next.js Documentation

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

### Getting Started

First, run the development server:

```bash
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.