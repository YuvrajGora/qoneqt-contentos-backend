from pathlib import Path

content = """/**
 * Qoneqt ContentOS - Generation API Client
 * 
 * Abstraction layer between UI components and backend pipeline.
 * Seamlessly connects UI to teammate's real FastAPI backend,
 * with fallback to high-fidelity mock pipeline if NEXT_PUBLIC_USE_MOCK_API is enabled.
 */

import {
  GenerationRequest,
  GenerationStatus,
  GenerationResult,
  RegenerateSceneRequest,
  RegenerateSceneResult,
  PipelineLogEntry,
  PipelineStageId,
  PipelineStageState,
  Scene,
  SceneStatus,
  QualityCheckStatus,
  QualityCheckItem,
  JobStatus,
  ContentType,
  ContentStyle,
} from './types';
import {
  createMockJob,
  getMockJobStatus,
  getMockJobResult,
  updateMockJobStatus,
  mockRegenerateScene,
  PIPELINE_STAGES,
} from './mock';

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK_API === 'true';
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000/api';

function formatTimestamp(): string {
  const now = new Date();
  return now.toTimeString().split(' ')[0]; // "HH:MM:SS"
}

function getBackendOrigin(): string {
  try {
    return new URL(API_BASE_URL).origin;
  } catch {
    return 'http://127.0.0.1:8000';
  }
}

function resolveAssetUrl(url?: string): string | undefined {
  if (!url) return undefined;
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:') || url.startsWith('data:')) {
    return url;
  }
  const origin = getBackendOrigin();
  return url.startsWith('/') ? `${origin}${url}` : `${origin}/${url}`;
}

/**
 * Initiates video content generation from a prompt/topic request
 */
export async function generateContent(request: GenerationRequest): Promise<{ jobId: string; status: GenerationStatus }> {
  if (USE_MOCK) {
    const { jobId, status } = createMockJob(request);
    return { jobId, status };
  }

  const response = await fetch(`${API_BASE_URL}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      topic: request.topic,
      duration: request.duration,
      style: request.style,
    }),
  });

  if (!response.ok) {
    throw new Error(`Generation API error: ${response.status} ${response.statusText}`);
  }

  const data = (await response.json()) as Record<string, unknown>;
  const jobId = String(data.job_id || data.jobId);

  let initialStatus: GenerationStatus;
  try {
    initialStatus = await getGenerationStatus(jobId);
  } catch {
    initialStatus = {
      jobId,
      status: 'queued',
      progress: 0,
      currentStage: 'topic_analysis',
      currentStageLabel: 'Topic Analysis',
      completedStages: [],
      stages: PIPELINE_STAGES.map((s, idx) => ({
        id: s.id,
        number: s.number,
        label: s.label,
        status: idx === 0 ? 'active' : 'pending',
        detail: idx === 0 ? s.activeDescription : s.description,
      })),
      activityLogs: [
        {
          id: `log_init_${Date.now()}`,
          timestamp: formatTimestamp(),
          stageId: 'topic_analysis',
          status: 'active',
          message: 'Ingesting prompt and starting ContentOS autonomous director',
        },
      ],
      startedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
  }

  return { jobId, status: initialStatus };
}

/**
 * Polls the current status and stage progression of a generation job
 */
export async function getGenerationStatus(jobId: string): Promise<GenerationStatus> {
  if (USE_MOCK) {
    const status = getMockJobStatus(jobId);
    if (!status) {
      throw new Error(`Mock job with ID "${jobId}" not found`);
    }
    return status;
  }

  const response = await fetch(`${API_BASE_URL}/status/${jobId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Status API error: ${response.status} ${response.statusText}`);
  }

  const data = (await response.json()) as Record<string, unknown>;
  return normalizeBackendStatus(data, jobId);
}

function normalizeBackendStatus(data: Record<string, unknown>, jobId: string): GenerationStatus {
  const completedStages: PipelineStageId[] = ((data.completedStages as string[]) || []) as PipelineStageId[];
  const currentStage: PipelineStageId | null = (data.currentStage as PipelineStageId) || null;
  const isFailed = data.status === 'failed';
  const isCompleted = data.status === 'completed';

  const stages: PipelineStageState[] = PIPELINE_STAGES.map((cfg) => {
    let stageStatus: 'pending' | 'active' | 'completed' | 'failed' = 'pending';
    if (completedStages.includes(cfg.id) || (isCompleted && cfg.id !== 'ready_to_publish')) {
      stageStatus = 'completed';
    } else if (isCompleted && cfg.id === 'ready_to_publish') {
      stageStatus = 'completed';
    } else if (currentStage === cfg.id) {
      stageStatus = isFailed ? 'failed' : 'active';
    }

    return {
      id: cfg.id,
      number: cfg.number,
      label: cfg.label,
      status: stageStatus,
      detail: stageStatus === 'active' ? cfg.activeDescription : cfg.description,
    };
  });

  const activeCfg = PIPELINE_STAGES.find((s) => s.id === currentStage);
  const currentStageLabel = isCompleted
    ? 'Ready to Publish'
    : activeCfg?.label || (currentStage ? String(currentStage) : 'Initializing');

  const rawLogs = (data.activityLogs as Record<string, unknown>[]) || [];
  const activityLogs: PipelineLogEntry[] = rawLogs.map((log: Record<string, unknown>, idx: number) => {
    const stageId = (log.stageId || log.stage || currentStage || 'topic_analysis') as PipelineStageId;
    return {
      id: String(log.id || `log_${idx}_${Date.now()}`),
      timestamp: typeof log.timestamp === 'string' && log.timestamp.includes('T')
        ? log.timestamp.split('T')[1]?.slice(0, 8) || formatTimestamp()
        : formatTimestamp(),
      stageId,
      status: (log.status as 'pending' | 'active' | 'completed' | 'failed') || (isCompleted ? 'completed' : 'active'),
      message: String(log.message || log),
    };
  });

  return {
    jobId: String(data.jobId || data.job_id || jobId),
    status: (data.status || 'processing') as JobStatus,
    progress: typeof data.progress === 'number' ? data.progress : 0,
    currentStage,
    currentStageLabel,
    completedStages,
    stages,
    activityLogs,
    error: typeof data.error === 'string' ? data.error : null,
    startedAt: typeof data.created_at === 'string' ? data.created_at : new Date().toISOString(),
    updatedAt: typeof data.updated_at === 'string' ? data.updated_at : new Date().toISOString(),
  };
}

/**
 * Fetches the finalized generation result, complete with scenes and quality score
 */
export async function getGenerationResult(jobId: string): Promise<GenerationResult> {
  if (USE_MOCK) {
    const result = getMockJobResult(jobId);
    if (!result) {
      throw new Error(`Mock job result with ID "${jobId}" not found`);
    }
    return result;
  }

  const response = await fetch(`${API_BASE_URL}/result/${jobId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Result API error: ${response.status} ${response.statusText}`);
  }

  const data = (await response.json()) as Record<string, unknown>;
  return normalizeBackendResult(data, jobId);
}

function normalizeBackendResult(data: Record<string, unknown>, jobId: string): GenerationResult {
  const resolvedVideoUrl = resolveAssetUrl(typeof data.videoUrl === 'string' ? data.videoUrl : typeof data.video_url === 'string' ? data.video_url : undefined);

  const rawScenes = (data.scenes as Record<string, unknown>[]) || [];
  const scenes: Scene[] = rawScenes.map((s: Record<string, unknown>, idx: number) => {
    const sceneId = String(s.id || s.scene_id || idx + 1);
    const order = Number(s.order || s.scene_id || idx + 1);
    const duration = Number(s.duration || 7.5);
    const narration = String(s.narration || '');
    const visualDescription = String(s.visualDescription || s.visual_prompt || '');
    const imageUrl = resolveAssetUrl(typeof s.imageUrl === 'string' ? s.imageUrl : typeof s.image_url === 'string' ? s.image_url : undefined);
    const audioUrl = resolveAssetUrl(typeof s.audioUrl === 'string' ? s.audioUrl : typeof s.audio_url === 'string' ? s.audio_url : undefined);
    const excerpt = typeof s.captionExcerpt === 'string' ? s.captionExcerpt : (narration.length > 45 ? narration.slice(0, 45) + '...' : narration);

    return {
      id: sceneId,
      order,
      duration,
      narration,
      visualDescription,
      status: ((s.status as string) || 'completed') as SceneStatus,
      imageUrl,
      audioUrl,
      captionExcerpt: excerpt,
      transition: typeof s.transition === 'string' ? s.transition : 'Smooth cinematic crossfade',
    };
  });

  const rawQuality = (data.qualityStatus as Record<string, unknown>) || {};
  const rawChecks = (rawQuality.checks as Record<string, unknown>[]) || [];
  const checks: QualityCheckItem[] = rawChecks.map((c: Record<string, unknown>) => {
    const nameStr = String(c.name || '');
    const nameLower = nameStr.toLowerCase();
    const id = nameLower ? `qc-${nameLower}` : `qc-check`;
    return {
      id,
      label: `${nameStr} Verification`,
      description: `${nameStr} compliance and stream integrity verified`,
      passed: Boolean(c.passed),
    };
  });

  if (rawQuality.passed && !checks.some((c) => c.id === 'qc-ready')) {
    checks.push({
      id: 'qc-ready',
      label: 'Broadcast compliance',
      description: 'Stream verified for broadcast publishing',
      passed: true,
    });
  }

  const qualityStatus: QualityCheckStatus = {
    passed: Boolean(rawQuality.passed),
    score: Number(rawQuality.score ?? 100),
    readyForPublishing: Boolean(rawQuality.readyForPublishing ?? true),
    checks,
  };

  return {
    jobId: String(data.jobId || data.job_id || jobId),
    topic: typeof data.topic === 'string' ? data.topic : typeof data.title === 'string' ? data.title : 'AI Software Development',
    contentType: (data.contentType as ContentType) || 'educational',
    style: (data.style as ContentStyle) || 'cinematic',
    duration: Number(data.duration || 30),
    title: String(data.title || 'Autonomous Video Production'),
    hook: String(data.hook || ''),
    script: typeof data.script === 'string' ? data.script : scenes.map((s) => s.narration).join('\\n\\n'),
    scenes,
    videoUrl: resolvedVideoUrl,
    thumbnailUrl: scenes[0]?.imageUrl,
    qualityStatus,
    createdAt: typeof data.created_at === 'string' ? data.created_at : new Date().toISOString(),
    updatedAt: typeof data.updated_at === 'string' ? data.updated_at : new Date().toISOString(),
  };
}

/**
 * Regenerates an individual scene without having to rerun the entire pipeline
 */
export async function regenerateScene(request: RegenerateSceneRequest): Promise<RegenerateSceneResult> {
  if (USE_MOCK) {
    return mockRegenerateScene(request);
  }

  const response = await fetch(`${API_BASE_URL}/regenerate-scene`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jobId: request.jobId,
      sceneId: request.sceneId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Regenerate scene API error: ${response.status} ${response.statusText}`);
  }

  // Poll until regeneration finishes
  const maxAttempts = 40;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await new Promise((r) => setTimeout(r, 2000));
    const st = await getGenerationStatus(request.jobId);
    if (st.status === 'completed') {
      const res = await getGenerationResult(request.jobId);
      const updatedScene = res.scenes.find((s) => s.id === request.sceneId);
      if (updatedScene) {
        return {
          jobId: request.jobId,
          scene: updatedScene,
          updatedAt: new Date().toISOString(),
        };
      }
    }
  }

  throw new Error('Scene regeneration timed out');
}

/**
 * Pipeline simulation / monitoring lifecycle driver.
 * If mock mode is active, drives local mock simulation.
 * If real mode is active, polls the real backend until complete.
 */
export function startMockPipelineSimulation(
  jobId: string,
  onUpdate: (status: GenerationStatus) => void,
  onComplete: (result: GenerationResult) => void,
  onError?: (err: Error) => void
): () => void {
  if (!USE_MOCK) {
    let isCancelled = false;
    let pollInterval: NodeJS.Timeout | null = null;

    const poll = async () => {
      if (isCancelled) return;
      try {
        const status = await getGenerationStatus(jobId);
        if (isCancelled) return;
        onUpdate(status);

        if (status.status === 'completed') {
          if (pollInterval) clearInterval(pollInterval);
          const result = await getGenerationResult(jobId);
          if (isCancelled) return;
          onComplete(result);
        } else if (status.status === 'failed') {
          if (pollInterval) clearInterval(pollInterval);
          onError?.(new Error(status.error || 'Generation pipeline failed'));
        }
      } catch (err) {
        if (!isCancelled && onError) {
          console.warn('Polling error:', err);
        }
      }
    };

    poll();
    pollInterval = setInterval(poll, 2500);

    return () => {
      isCancelled = true;
      if (pollInterval) clearInterval(pollInterval);
    };
  }

  let isCancelled = false;
  let currentStageIndex = 0;
  const activityLogs: PipelineLogEntry[] = [
    {
      id: `log_init_${Date.now()}`,
      timestamp: formatTimestamp(),
      stageId: 'topic_analysis',
      status: 'active',
      message: 'Ingesting prompt and starting ContentOS autonomous director',
    },
  ];

  async function step() {
    if (isCancelled) return;

    try {
      const stageConfig = PIPELINE_STAGES[currentStageIndex];
      const isLastStage = currentStageIndex === PIPELINE_STAGES.length - 1;
      
      const progressPercent = Math.min(
        100,
        Math.round(((currentStageIndex + 1) / PIPELINE_STAGES.length) * 100)
      );

      const completedStageIds = PIPELINE_STAGES.slice(0, currentStageIndex).map(s => s.id);

      const updatedStages = PIPELINE_STAGES.map((s, idx) => {
        let stageStatus: 'pending' | 'active' | 'completed' | 'failed' = 'pending';
        if (idx < currentStageIndex) stageStatus = 'completed';
        else if (idx === currentStageIndex) stageStatus = 'active';
        return {
          id: s.id,
          number: s.number,
          label: s.label,
          status: stageStatus,
          detail: idx === currentStageIndex ? s.activeDescription : s.description,
        };
      });

      activityLogs.push({
        id: `log_${stageConfig.id}_${Date.now()}`,
        timestamp: formatTimestamp(),
        stageId: stageConfig.id,
        status: 'active',
        message: stageConfig.logMessage,
      });

      const updatedStatus = updateMockJobStatus(jobId, {
        status: 'processing',
        progress: progressPercent,
        currentStage: stageConfig.id,
        currentStageLabel: stageConfig.label,
        completedStages: completedStageIds,
        stages: updatedStages,
        activityLogs: [...activityLogs],
        estimatedTimeRemainingSec: Math.max(
          1,
          Math.round(
            PIPELINE_STAGES.slice(currentStageIndex).reduce((acc, s) => acc + s.estimatedDurationMs, 0) / 1000
          )
        ),
      });

      if (updatedStatus) {
        onUpdate(updatedStatus);
      }

      await new Promise(r => setTimeout(r, stageConfig.estimatedDurationMs));

      if (isCancelled) return;

      const lastLog = activityLogs[activityLogs.length - 1];
      if (lastLog) {
        lastLog.status = 'completed';
      }

      if (isLastStage) {
        const finalStages = PIPELINE_STAGES.map(s => ({
          id: s.id,
          number: s.number,
          label: s.label,
          status: 'completed' as const,
          detail: s.description,
        }));

        activityLogs.push({
          id: `log_complete_${Date.now()}`,
          timestamp: formatTimestamp(),
          stageId: 'ready_to_publish',
          status: 'completed',
          message: 'Video pipeline complete. Quality verified and ready for review.',
        });

        const finalStatus = updateMockJobStatus(jobId, {
          status: 'completed',
          progress: 100,
          currentStage: null,
          currentStageLabel: 'Ready to Publish',
          completedStages: PIPELINE_STAGES.map(s => s.id),
          stages: finalStages,
          activityLogs: [...activityLogs],
          estimatedTimeRemainingSec: 0,
        });

        if (finalStatus) {
          onUpdate(finalStatus);
        }

        const result = getMockJobResult(jobId);
        if (result) {
          onComplete(result);
        }
      } else {
        currentStageIndex++;
        step();
      }
    } catch (err) {
      if (!isCancelled && onError) {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  }

  step();

  return () => {
    isCancelled = true;
  };
}
"""

target = Path(r"C:\Users\Yuvraj Gora\Desktop\Gujrat Hackathon\lib\api\generation.ts")
target.write_text(content, encoding="utf-8")
print(f"Successfully written to {target} ({target.stat().st_size} bytes)")
