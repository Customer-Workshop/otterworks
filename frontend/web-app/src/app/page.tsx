export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="flex flex-col items-center justify-center min-h-screen">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          OtterWorks
        </h1>
        <p className="text-xl text-gray-600 mb-8">
          Collaborative Document & File Management
        </p>
        <div className="flex gap-4">
          <a
            href="/login"
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            Sign In
          </a>
          <a
            href="/register"
            className="px-6 py-3 bg-white text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition"
          >
            Register
          </a>
        </div>
      </div>
    </main>
  );
}
