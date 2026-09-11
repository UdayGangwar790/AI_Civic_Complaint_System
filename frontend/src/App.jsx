import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';

function App() {
  return (
    <Router>
      <div className="min-h-screen flex flex-col">
        <header className="bg-blue-600 text-white p-4 shadow-md">
          <div className="container mx-auto flex justify-between items-center">
            <h1 className="text-2xl font-bold">CVKI Platform</h1>
            <nav>
              <ul className="flex space-x-4">
                <li><Link to="/" className="hover:underline">Home</Link></li>
                <li><Link to="/dashboard" className="hover:underline">Dashboard</Link></li>
                <li><Link to="/report" className="hover:underline">Report Problem</Link></li>
              </ul>
            </nav>
          </div>
        </header>

        <main className="flex-grow container mx-auto p-4">
          <Routes>
            <Route path="/" element={
              <div className="text-center mt-10">
                <h2 className="text-4xl font-extrabold mb-4 text-gray-800">Civic Vision & Knowledge Intelligence</h2>
                <p className="text-lg text-gray-600 mb-8">Empowering citizens to report civic problems easily.</p>
                <div className="bg-yellow-100 border-l-4 border-yellow-500 text-yellow-700 p-4 inline-block text-left max-w-lg">
                  <p className="font-bold">Foundation Phase Active</p>
                  <p>AI Computer Vision module is currently a placeholder. Training and integration will be implemented in the future.</p>
                </div>
              </div>
            } />
            <Route path="/dashboard" element={
              <div>
                <h2 className="text-2xl font-bold mb-4">Citizen Dashboard</h2>
                <p>Placeholder for complaint history and status tracking.</p>
              </div>
            } />
            <Route path="/report" element={
              <div>
                <h2 className="text-2xl font-bold mb-4">Report a Civic Problem</h2>
                <div className="bg-white p-6 rounded-lg shadow-md border border-gray-200 max-w-md">
                  <p className="mb-4 text-sm text-gray-600">Upload an image of the civic problem. The system will (later) automatically detect the issue.</p>
                  <input type="file" className="block w-full text-sm text-gray-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-blue-50 file:text-blue-700
                    hover:file:bg-blue-100
                  " disabled/>
                  <p className="text-red-500 text-xs mt-2 italic">*AI detection is not yet implemented.</p>
                </div>
              </div>
            } />
          </Routes>
        </main>
        
        <footer className="bg-gray-800 text-white text-center p-4">
          <p>&copy; {new Date().getFullYear()} CVKI. All rights reserved.</p>
        </footer>
      </div>
    </Router>
  );
}

export default App;
