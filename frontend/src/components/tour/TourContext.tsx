import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { useAuthStore } from '../../stores/authStore';
import { TOUR_STEPS } from './tourConfig';
import { TourOverlay } from './TourOverlay';
import type { TourPathMatch, TourRole, TourStep } from './types';

interface TourContextValue {
  isActive: boolean;
  startTour: () => void;
}

const TourContext = React.createContext<TourContextValue>({
  isActive: false,
  startTour: () => {},
});

const TOUR_COMPLETED_PREFIX = 'lms:tour:completed';
const TOUR_COMPLETED_PREFIX_V2 = 'lms:tour:completed:v2';
const TOUR_AUTOSTART_SESSION_PREFIX = 'lms:tour:autostarted:v1';
const DEFAULT_SELECTOR_MISS_MESSAGE =
  "Couldn't locate this element yet. Complete page load or click Next to continue.";
const AUTO_NAV_COOLDOWN_MS = 700;
const AUTO_NAV_BURST_WINDOW_MS = 10_000;
const AUTO_NAV_BURST_LIMIT = 12;
const AUTO_NAV_STEP_ATTEMPT_LIMIT = 1;

function getTourRole(role?: string | null): TourRole | null {
  if (!role) return null;
  if (role === 'SUPER_ADMIN') return 'SUPER_ADMIN';
  if (role === 'SCHOOL_ADMIN') return 'SCHOOL_ADMIN';
  return 'TEACHER';
}

function getDashboardRouteForRole(role: TourRole): string {
  if (role === 'SUPER_ADMIN') return '/super-admin/dashboard';
  if (role === 'SCHOOL_ADMIN') return '/admin/dashboard';
  return '/teacher/dashboard';
}

function getTourHostScope(): string {
  const host = window.location.hostname.toLowerCase();
  return host.startsWith('www.') ? host.slice(4) : host;
}

function getTourCompletionKey(userId: string, role: TourRole): string {
  return `${TOUR_COMPLETED_PREFIX_V2}:${getTourHostScope()}:${userId}:${role}`;
}

function getCandidateTourCompletionKeys(userId: string, role: TourRole): string[] {
  const host = window.location.hostname.toLowerCase();
  const normalizedHost = getTourHostScope();
  const keys = [`${TOUR_COMPLETED_PREFIX_V2}:${normalizedHost}:${userId}:${role}`];
  if (host !== normalizedHost) {
    keys.push(`${TOUR_COMPLETED_PREFIX_V2}:${host}:${userId}:${role}`);
  }
  return keys;
}

function getTourAutostartSessionKey(userId: string, role: TourRole): string {
  return `${TOUR_AUTOSTART_SESSION_PREFIX}:${getTourHostScope()}:${userId}:${role}`;
}

function hasLegacyTourCompletion(userId: string, role: TourRole): boolean {
  const legacyPrefix = `${TOUR_COMPLETED_PREFIX}:${userId}:${role}:`;
  for (let idx = 0; idx < localStorage.length; idx += 1) {
    const key = localStorage.key(idx);
    if (!key || !key.startsWith(legacyPrefix)) continue;
    if (localStorage.getItem(key) === '1') {
      return true;
    }
  }
  return false;
}

function isTourCompleted(userId: string, role: TourRole): boolean {
  for (const key of getCandidateTourCompletionKeys(userId, role)) {
    if (localStorage.getItem(key) === '1') {
      return true;
    }
  }
  return hasLegacyTourCompletion(userId, role);
}

function routeMatches(pathname: string, search: string, route: string, pathMatch: TourPathMatch = 'exact'): boolean {
  const [targetPath, targetQuery = ''] = route.split('?');
  const pathMatches = pathMatch === 'startsWith' ? pathname.startsWith(targetPath) : pathname === targetPath;
  if (!pathMatches) return false;
  if (!targetQuery) return true;

  const current = new URLSearchParams(search);
  const required = new URLSearchParams(targetQuery);
  for (const [key, value] of required.entries()) {
    if (current.get(key) !== value) return false;
  }
  return true;
}

function resolveRoute(step: TourStep): string | null {
  if (typeof step.path === 'function') return step.path();
  return step.path;
}

function normalizeRoute(route: string): string {
  const [path, query = ''] = route.split('?');
  if (!query) return path;

  const sortedEntries = Array.from(new URLSearchParams(query).entries()).sort(([leftKey, leftValue], [rightKey, rightValue]) => {
    if (leftKey === rightKey) {
      return leftValue.localeCompare(rightValue);
    }
    return leftKey.localeCompare(rightKey);
  });

  const normalized = new URLSearchParams();
  for (const [key, value] of sortedEntries) {
    normalized.append(key, value);
  }

  const normalizedQuery = normalized.toString();
  return normalizedQuery ? `${path}?${normalizedQuery}` : path;
}

function findVisibleElement(selector: string): HTMLElement | null {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>(selector));
  return (
    candidates.find((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      const style = window.getComputedStyle(el);
      return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }) || null
  );
}

function waitForElement(selector: string, timeoutMs: number): Promise<HTMLElement | null> {
  return new Promise((resolve) => {
    const start = Date.now();

    const tick = () => {
      const found = findVisibleElement(selector);
      if (found) {
        resolve(found);
        return;
      }
      if (Date.now() - start >= timeoutMs) {
        resolve(null);
        return;
      }
      requestAnimationFrame(tick);
    };

    tick();
  });
}

function isTourDebugEnabled(): boolean {
  return localStorage.getItem('lpTourDebug') === '1';
}

function logTourDebug(event: string, payload?: Record<string, unknown>) {
  if (!isTourDebugEnabled()) return;
  // eslint-disable-next-line no-console
  console.info(`[tour] ${event}`, payload ?? {});
}

function getMissingBehavior(step: TourStep): NonNullable<TourStep['onMissing']> {
  return step.onMissing ?? 'pause';
}

function shouldAutostartTour(role: TourRole, pathname: string): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return true;
  }
  if (!window.matchMedia('(min-width: 1024px)').matches) {
    return false;
  }
  return pathname === getDashboardRouteForRole(role);
}

export const TourProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated } = useAuthStore();
  const [activeRole, setActiveRole] = React.useState<TourRole | null>(null);
  const [activeStepIndex, setActiveStepIndex] = React.useState(0);
  const [targetElement, setTargetElement] = React.useState<HTMLElement | null>(null);
  const [targetRect, setTargetRect] = React.useState<DOMRect | null>(null);
  const [isResolving, setIsResolving] = React.useState(false);
  const [blockedReason, setBlockedReason] = React.useState<string | null>(null);
  const [navigationPausedReason, setNavigationPausedReason] = React.useState<string | null>(null);

  const role = getTourRole(user?.role);
  const isActive = Boolean(activeRole);
  const steps = React.useMemo(() => (activeRole ? TOUR_STEPS[activeRole] : []), [activeRole]);
  const currentStep = steps[activeStepIndex];

  const lastAutoNavigationRef = React.useRef<{ targetRoute: string; at: number } | null>(null);
  const autoNavigationBurstRef = React.useRef<number[]>([]);
  const stepNavigationAttemptRef = React.useRef<
    Record<string, { targetRoute: string; count: number }>
  >({});

  const markCurrentTourComplete = React.useCallback(() => {
    if (!user?.id || !activeRole) return;
    localStorage.setItem(getTourCompletionKey(user.id, activeRole), '1');
    logTourDebug('tour_completed', { role: activeRole, userId: user.id, host: window.location.hostname });
  }, [activeRole, user?.id]);

  const closeTour = React.useCallback(
    (markComplete: boolean) => {
      if (markComplete) {
        markCurrentTourComplete();
      }
      setActiveRole(null);
      setActiveStepIndex(0);
      setTargetElement(null);
      setTargetRect(null);
      setIsResolving(false);
      setBlockedReason(null);
      setNavigationPausedReason(null);
      lastAutoNavigationRef.current = null;
      autoNavigationBurstRef.current = [];
      stepNavigationAttemptRef.current = {};
    },
    [markCurrentTourComplete]
  );

  const startTour = React.useCallback(() => {
    const nextRole = getTourRole(user?.role);
    if (!isAuthenticated || !nextRole) return;
    setActiveRole(nextRole);
    setActiveStepIndex(0);
    setBlockedReason(null);
    setNavigationPausedReason(null);
    lastAutoNavigationRef.current = null;
    autoNavigationBurstRef.current = [];
    stepNavigationAttemptRef.current = {};
  }, [isAuthenticated, user?.role]);

  const nextStep = React.useCallback(() => {
    if (!currentStep) return;
    if (activeStepIndex >= steps.length - 1) {
      closeTour(true);
      return;
    }
    setBlockedReason(null);
    setNavigationPausedReason(null);
    stepNavigationAttemptRef.current = {};
    setActiveStepIndex((prev) => prev + 1);
  }, [activeStepIndex, closeTour, currentStep, steps.length]);

  const prevStep = React.useCallback(() => {
    setBlockedReason(null);
    setNavigationPausedReason(null);
    stepNavigationAttemptRef.current = {};
    setActiveStepIndex((prev) => Math.max(0, prev - 1));
  }, []);

  React.useEffect(() => {
    if (!isAuthenticated || !user?.id || !role || isActive) return;
    if (!shouldAutostartTour(role, location.pathname)) return;
    if (isTourCompleted(user.id, role)) return;
    const sessionAutostartKey = getTourAutostartSessionKey(user.id, role);
    if (sessionStorage.getItem(sessionAutostartKey) === '1') return;
    sessionStorage.setItem(sessionAutostartKey, '1');
    setActiveRole(role);
    setActiveStepIndex(0);
    logTourDebug('tour_autostart', { role, userId: user.id });
  }, [isActive, isAuthenticated, location.pathname, role, user?.id]);

  const handleMissingStep = React.useCallback(
    (step: TourStep, context: 'route' | 'selector') => {
      const behavior = getMissingBehavior(step);
      logTourDebug('step_missing', { stepId: step.id, behavior, context });

      if (behavior === 'skip') {
        setIsResolving(false);
        nextStep();
        return;
      }

      if (behavior === 'stop') {
        closeTour(false);
        return;
      }

      setBlockedReason(DEFAULT_SELECTOR_MISS_MESSAGE);
      setIsResolving(false);
    },
    [closeTour, nextStep]
  );

  const canAutoNavigate = React.useCallback(
    (stepId: string, targetRoute: string): boolean => {
      if (navigationPausedReason) {
        setBlockedReason(navigationPausedReason);
        return false;
      }

      const now = Date.now();
      const normalizedTargetRoute = normalizeRoute(targetRoute);
      const normalizedCurrentRoute = normalizeRoute(`${location.pathname}${location.search}`);
      if (normalizedCurrentRoute === normalizedTargetRoute) {
        return false;
      }

      const existingStepAttempt = stepNavigationAttemptRef.current[stepId];
      if (existingStepAttempt && existingStepAttempt.targetRoute === normalizedTargetRoute) {
        if (existingStepAttempt.count >= AUTO_NAV_STEP_ATTEMPT_LIMIT) {
          const reason =
            'Automatic tour navigation paused on this step to avoid redirect loops. Use Next or Back to continue manually.';
          setNavigationPausedReason(reason);
          setBlockedReason(reason);
          setIsResolving(false);
          logTourDebug('route_step_paused', {
            stepId,
            targetRoute: normalizedTargetRoute,
            count: existingStepAttempt.count,
          });
          return false;
        }
        existingStepAttempt.count += 1;
      } else {
        stepNavigationAttemptRef.current[stepId] = {
          targetRoute: normalizedTargetRoute,
          count: 1,
        };
      }

      const lastNavigation = lastAutoNavigationRef.current;
      if (
        lastNavigation &&
        lastNavigation.targetRoute === normalizedTargetRoute &&
        now - lastNavigation.at <= AUTO_NAV_COOLDOWN_MS
      ) {
        logTourDebug('route_deduped', { targetRoute: normalizedTargetRoute, deltaMs: now - lastNavigation.at });
        return false;
      }

      const recent = autoNavigationBurstRef.current.filter(
        (timestamp) => now - timestamp <= AUTO_NAV_BURST_WINDOW_MS
      );
      recent.push(now);
      autoNavigationBurstRef.current = recent;

      if (recent.length > AUTO_NAV_BURST_LIMIT) {
        const reason =
          'Automatic tour navigation paused to avoid rapid route changes. Use Next or Back to continue manually.';
        setNavigationPausedReason(reason);
        setBlockedReason(reason);
        setIsResolving(false);
        logTourDebug('route_burst_paused', {
          targetRoute: normalizedTargetRoute,
          countInWindow: recent.length,
          windowMs: AUTO_NAV_BURST_WINDOW_MS,
        });
        return false;
      }

      lastAutoNavigationRef.current = { targetRoute: normalizedTargetRoute, at: now };
      return true;
    },
    [location.pathname, location.search, navigationPausedReason]
  );

  React.useEffect(() => {
    if (!isActive || !currentStep) return;
    let cancelled = false;

    const run = async () => {
      setIsResolving(true);
      setTargetElement(null);
      setTargetRect(null);
      setBlockedReason(null);

      const resolvedRoute = resolveRoute(currentStep);
      const targetRoute = resolvedRoute || currentStep.fallbackPath || null;

      if (!targetRoute) {
        handleMissingStep(currentStep, 'route');
        return;
      }

      if (!routeMatches(location.pathname, location.search, targetRoute, currentStep.pathMatch)) {
        if (!canAutoNavigate(currentStep.id, targetRoute)) {
          setIsResolving(false);
          return;
        }

        logTourDebug('route_navigate', {
          stepId: currentStep.id,
          fromPathname: location.pathname,
          fromSearch: location.search,
          targetRoute,
        });
        navigate(targetRoute, { replace: true });
        return;
      }

      delete stepNavigationAttemptRef.current[currentStep.id];

      if (!currentStep.selector) {
        setIsResolving(false);
        return;
      }

      const waitMs = currentStep.waitMs ?? 3500;
      const element = await waitForElement(currentStep.selector, waitMs);
      if (cancelled) return;

      if (!element) {
        logTourDebug('selector_timeout', {
          stepId: currentStep.id,
          selector: currentStep.selector,
          waitMs,
        });
        handleMissingStep(currentStep, 'selector');
        return;
      }

      element.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      });
      if (cancelled) return;

      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        setTargetElement(null);
        setTargetRect(null);
        handleMissingStep(currentStep, 'selector');
        return;
      }

      setTargetElement(element);
      setTargetRect(rect);
      setIsResolving(false);
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [
    canAutoNavigate,
    currentStep,
    handleMissingStep,
    isActive,
    location.pathname,
    location.search,
    navigate,
  ]);

  React.useEffect(() => {
    if (!isActive || !targetElement) return;

    let frameId: number | null = null;

    const scheduleRectUpdate = () => {
      if (frameId !== null) return;
      frameId = requestAnimationFrame(() => {
        frameId = null;
        const rect = targetElement.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
          setTargetRect(null);
          return;
        }
        setTargetRect(rect);
      });
    };

    scheduleRectUpdate();
    const resizeObserver = new ResizeObserver(scheduleRectUpdate);
    resizeObserver.observe(targetElement);
    window.addEventListener('resize', scheduleRectUpdate);
    window.addEventListener('scroll', scheduleRectUpdate, true);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', scheduleRectUpdate);
      window.removeEventListener('scroll', scheduleRectUpdate, true);
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }
    };
  }, [isActive, targetElement]);

  React.useEffect(() => {
    if (!isActive) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isActive]);

  React.useEffect(() => {
    if (!isActive) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeTour(true);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [closeTour, isActive]);

  return (
    <TourContext.Provider value={{ isActive, startTour }}>
      {children}
      {isActive &&
        currentStep &&
        createPortal(
          <TourOverlay
            step={currentStep}
            stepNumber={activeStepIndex + 1}
            totalSteps={steps.length}
            targetRect={targetRect}
            isResolving={isResolving}
            blockedReason={blockedReason}
            onBack={prevStep}
            onNext={nextStep}
            onSkip={() => closeTour(true)}
          />,
          document.body
        )}
    </TourContext.Provider>
  );
};

export const useGuidedTour = (): TourContextValue => React.useContext(TourContext);
