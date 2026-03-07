import { defineStore } from 'pinia'
import { shallowRef, triggerRef } from 'vue'
import type { CaptureJob } from '@/types'

export const useJobsStore = defineStore('jobs', () => {
  const jobs = shallowRef<Map<string, CaptureJob>>(new Map())

  const _completionCallbacks = new Set<(urlId: string) => void>()

  function handleInit(activeJobs: CaptureJob[]) {
    jobs.value = new Map(activeJobs.map(j => [j.id, j]))
  }

  function handleJobUpdate(job: CaptureJob) {
    jobs.value.set(job.id, job)
    triggerRef(jobs)

    if (job.status === 'completed' || job.status === 'failed') {
      _completionCallbacks.forEach(cb => cb(job.url_id))
      setTimeout(() => {
        jobs.value.delete(job.id)
        triggerRef(jobs)
      }, 4000)
    }
  }

  function jobsForUrl(urlId: string): CaptureJob[] {
    return Array.from(jobs.value.values()).filter(j => j.url_id === urlId)
  }

  function hasActiveJobs(urlId: string): boolean {
    return Array.from(jobs.value.values()).some(
      j => j.url_id === urlId && (j.status === 'pending' || j.status === 'running')
    )
  }

  function onCompletion(cb: (urlId: string) => void): () => void {
    _completionCallbacks.add(cb)
    return () => _completionCallbacks.delete(cb)
  }

  return { jobs, handleInit, handleJobUpdate, jobsForUrl, hasActiveJobs, onCompletion }
})
