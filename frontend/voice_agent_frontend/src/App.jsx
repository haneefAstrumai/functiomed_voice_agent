// import { useState } from 'react'
// import VoiceAgent from './VoiceAgent'

// export default function App() {
//   // Simple hash-based routing — no extra library needed
//   const isAdmin = window.location.pathname === '/admin'

//   if (isAdmin) {
//     // Admin page will be built on Day 4
//     return (
//       <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
//         <h1>Admin Dashboard</h1>
//         <p>Coming on Day 4.</p>
//       </div>
//     )
//   }

//   return <VoiceAgent />
// }

import VoiceAgent from './VoiceAgent'
import Admin from './Admin'

export default function App() {
  const isAdmin = window.location.pathname === '/admin'
  return isAdmin ? <Admin /> : <VoiceAgent />
}