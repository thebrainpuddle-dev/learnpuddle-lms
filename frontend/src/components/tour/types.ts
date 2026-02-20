export type TourPlacement = 'top' | 'right' | 'bottom' | 'left' | 'center';

export type TourRoute = string | (() => string | null);

export type TourPathMatch = 'exact' | 'startsWith';

export interface TourStep {
  id: string;
  title: string;
  description: string;
  path: TourRoute;
  fallbackPath?: string;
  selector?: string;
  placement?: TourPlacement;
  optional?: boolean;
  waitMs?: number;
  pathMatch?: TourPathMatch;
}

export type TourRole = 'SUPER_ADMIN' | 'SCHOOL_ADMIN' | 'TEACHER';
