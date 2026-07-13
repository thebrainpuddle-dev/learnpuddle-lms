import React from 'react';
import { AlertCircle, LoaderCircle, RotateCw } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { openmaicForkApi } from '../../services/openmaicService';
import { useTenantStore } from '../../stores/tenantStore';

interface Props {
  action: 'library' | 'create' | 'classroom';
  classroomId?: string;
  legacy: React.ReactNode;
}

export function OpenMAICRuntimeRoute({ action, classroomId, legacy }: Props) {
  const runtime = useTenantStore((state) => state.aiClassroomRuntime);
  const [attempt, setAttempt] = React.useState(0);
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    if (runtime !== 'openmaic_fork') return;
    let active = true;
    setError('');
    openmaicForkApi
      .launch({
        action,
        ...(classroomId ? { classroom_id: classroomId } : {}),
        return_path: `${window.location.pathname}${window.location.search}`,
      })
      .then(({ data }) => {
        if (active) window.location.assign(data.launch_url);
      })
      .catch((requestError) => {
        if (!active) return;
        setError(
          requestError?.response?.data?.error ||
            'AI Classroom could not be opened. Please try again.',
        );
      });
    return () => {
      active = false;
    };
  }, [action, attempt, classroomId, runtime]);

  if (runtime === 'legacy') return <>{legacy}</>;
  if (error) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center px-6">
        <div className="max-w-md text-center">
          <AlertCircle className="mx-auto mb-3 h-8 w-8 text-red-600" aria-hidden="true" />
          <h1 className="text-lg font-semibold text-gray-900">AI Classroom unavailable</h1>
          <p className="mt-2 text-sm text-gray-600">{error}</p>
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className="mt-5 inline-flex items-center gap-2 bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            <RotateCw className="h-4 w-4" aria-hidden="true" />
            Try again
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex min-h-[50vh] items-center justify-center" aria-live="polite">
      <LoaderCircle className="h-8 w-8 animate-spin text-primary-600" aria-hidden="true" />
      <span className="sr-only">Opening AI Classroom</span>
    </div>
  );
}

export function MAICClassroomRuntimeRoute({ legacy }: { legacy: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  return <OpenMAICRuntimeRoute action="classroom" classroomId={id} legacy={legacy} />;
}
