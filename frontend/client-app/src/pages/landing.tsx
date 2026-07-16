export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50">
      {/* Hero */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-otter-600 to-otter-800" />
        <div className="relative max-w-5xl mx-auto px-4 py-24 sm:py-32 text-center">
          <div className="flex items-center justify-center gap-3 mb-6">
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center backdrop-blur">
              <span className="text-white font-bold text-xl">OW</span>
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold text-white">
              OtterWorks
            </h1>
          </div>
          <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
            Collaborative document and file management for modern teams. Store,
            share, and edit together in real time.
          </p>
          <div className="flex items-center justify-center gap-4">
            <a
              href="/login"
              className="px-8 py-3 bg-white text-otter-700 rounded-xl hover:bg-gray-100 transition font-semibold text-sm shadow-lg"
            >
              Sign In
            </a>
            <a
              href="/register"
              className="px-8 py-3 bg-white/10 text-white border border-white/30 rounded-xl hover:bg-white/20 transition font-semibold text-sm backdrop-blur"
            >
              Create Account
            </a>
          </div>
        </div>
      </div>

      {/* Features */}
      <div className="max-w-5xl mx-auto px-4 py-20">
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-12">
          Everything you need for team collaboration
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
          <FeatureCard
            title="File Management"
            description="Upload, organize, and share files with drag-and-drop simplicity. Folder trees, version history, and instant preview."
          />
          <FeatureCard
            title="Document Editing"
            description="Rich text editor with real-time collaboration. See cursors, track changes, and work together seamlessly."
          />
          <FeatureCard
            title="Real-time Collaboration"
            description="Work with your team simultaneously. See who is online, share instantly, and stay in sync."
          />
          <FeatureCard
            title="Powerful Search"
            description="Find anything in seconds. Full-text search across files and documents with smart filters."
          />
          <FeatureCard
            title="Secure Sharing"
            description="Granular permissions for every file and document. Control who can view, edit, or manage your content."
          />
          <FeatureCard
            title="Instant Notifications"
            description="Stay informed with real-time notifications for shares, comments, mentions, and edits."
          />
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-4 py-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-otter-600 rounded-md flex items-center justify-center">
              <span className="text-white font-bold text-[10px]">OW</span>
            </div>
            <span className="text-sm text-gray-500">OtterWorks</span>
          </div>
          <p className="text-xs text-gray-400">
            Collaborative document &amp; file management platform
          </p>
        </div>
      </footer>
    </main>
  );
}

function FeatureCard({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="p-6 bg-white rounded-xl border border-gray-200 hover:shadow-md transition">
      <h3 className="text-base font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
    </div>
  );
}
