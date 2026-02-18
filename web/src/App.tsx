import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <div className="flex items-center justify-center h-screen">
          <div className="text-center">
            <h1 className="text-4xl font-bold mb-2">Training Assistant</h1>
            <p className="text-gray-400">Dashboard coming soon</p>
          </div>
        </div>
      </div>
    </QueryClientProvider>
  )
}

export default App
