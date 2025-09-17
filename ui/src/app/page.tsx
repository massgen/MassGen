'use client'

import NewCommandCenter from '@/components/NewCommandCenter'
import GridLayout from '@/components/GridLayout'
import DemoSimulation from '@/components/DemoSimulation'

export default function Home() {
  return (
    <div className="h-screen bg-gray-900 text-white">
      {/* Command Center - Fixed at top */}
      <NewCommandCenter />
      
      {/* Main Grid Layout - Account for command center height */}
      <div className="pt-16">
        <GridLayout />
      </div>

      {/* Demo simulation button */}
      <DemoSimulation />
    </div>
  )
}