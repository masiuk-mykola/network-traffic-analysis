import { notFound } from 'next/navigation'

import { StatesGallery } from './states-gallery'

/** Every state in one place, for the e2e suite and for looking at. Never in production. */
export default function StatesGalleryPage() {
  if (process.env.NODE_ENV === 'production') notFound()

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6">
      <h1 className="text-xl font-semibold">States</h1>
      <StatesGallery />
    </main>
  )
}
