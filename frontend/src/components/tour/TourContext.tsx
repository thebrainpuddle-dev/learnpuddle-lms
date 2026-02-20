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

function getTourRole(role?: string | null): TourRole | null {
  if (!role) return null;
  if (role === 'SUPER_ADMIN') return 'SUPER_ADMIN';
  if (role === 'SCHOOL_ADMIN') return 'SCHOOL_ADMIN';
  return 'TEACHER';
}

function getTourCompletionKey(userId: string, token: string, role: TourRole): string {
  return `${TOUR_COMPLETED_PREFIX}:${userId}:${role}:${token.slice(-24)}`;
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

export const TourProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, accessToken, isAuthenticated } = useAuthStore();
  const [activeRole, setActiveRole] = React.useState<TourRole | null>(null);
  const [activeStepIndex, setActiveStepIndex] = React.useState(0);
  const [targetElement, setTargetElement] = React.useState<HTMLElement | null>(null);
  const [targetRect, setTargetRect] = React.useState<DOMRect | null>(null);
  const [isResolving, setIsResolving] = React.useState(false);

  const role = getTourRole(user?.role);
  const isActive = Boolean(activeRole);
  const steps = React.useMemo(() => (activeRole ? TOUR_STEPS[activeRole] : []), [activeRole]);
  const currentStep = steps[activeStepIndex];

  const markCurrentTourComplete = React.useCallback(() => {
    if (!user?.id || !accessToken || !activeRole) return;
    localStorage.setItem(getTourCompletionKey(user.id, accessToken, activeRole), '1');
  }, [accessToken, activeRole, user?.id]);

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
    },
    [markCurrentTourComplete]
  );

  const startTour = React.useCallback(() => {
    const nextRole = getTourRole(user?.role);
    if (!isAuthenticated || !nextRole) return;
    setActiveRole(nextRole);
    setActiveStepIndex(0);
  }, [isAuthenticated, user?.role]);

  const nextStep = React.useCallback(() => {
    if (!currentStep) return;
    if (activeStepIndex >= steps.length - 1) {
      closeTour(true);
      return;
    }
    setActiveStepIndex((prev) => prev + 1);
  }, [activeStepIndex, closeTour, currentStep, steps.length]);

  const prevStep = React.useCallback(() => {
    setActiveStepIndex((prev) => Math.max(0, prev - 1));
  }, []);

  React.useEffect(() => {
    if (!isAuthenticated || !user?.id || !accessToken || !role || isActive) return;
    const key = getTourCompletionKey(user.id, accessToken, role);
    if (localStorage.getItem(key) === '1') return;
    setActiveRole(role);
    setActiveStepIndex(0);
  }, [accessToken, isActive, isAuthenticated, role, user?.id]);

  React.useEffect(() => {
    if (!isActive || !currentStep) return;
    let cancelled = false;

    const run = async () => {
      setIsResolving(true);
      setTargetElement(null);
      setTargetRect(null);

      const resolvedRoute = resolveRoute(currentStep);
      const targetRoute = resolvedRoute || currentStep.fallbackPath || null;

      if (!targetRoute) {
        if (currentStep.optional) {
          nextStep();
          return;
        }
        setIsResolving(false);
        return;
      }

      if (!routeMatches(location.pathname, location.search, targetRoute, currentStep.pathMatch)) {
        navigate(targetRoute);
        return;
      }

      if (!currentStep.selector) {
        setIsResolving(false);
        return;
      }

      const element = await waitForElement(currentStep.selector, currentStep.waitMs ?? 3500);
      if (cancelled) return;

      if (!element) {
        if (currentStep.optional) {
          nextStep();
          return;
        }
        setIsResolving(false);
        return;
      }

      element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      setTargetElement(element);
      setTargetRect(element.getBoundingClientRect());
      setIsResolving(false);
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [currentStep, isActive, location.pathname, location.search, navigate, nextStep]);

  React.useEffect(() => {
    if (!isActive || !targetElement) return;

    const updateRect = () => {
      const rect = targetElement.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        setTargetRect(null);
        return;
      }
      setTargetRect(rect);
    };

    updateRect();
    const resizeObserver = new ResizeObserver(updateRect);
    resizeObserver.observe(targetElement);
    window.addEventListener('resize', updateRect);
    window.addEventListener('scroll', updateRect, true);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateRect);
      window.removeEventListener('scroll', updateRect, true);
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

