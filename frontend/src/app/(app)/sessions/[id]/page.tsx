export default async function SessionPage({ params }: PageProps<'/sessions/[id]'>) {
  const { id } = await params

  return (
    <main className="flex flex-1 flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold">Session {id}</h1>
      <p className="text-sm text-gray-500">Transaction view comes next.</p>
    </main>
  )
}
