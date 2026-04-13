// src/components/ui/index.ts
//
// Barrel export for shadcn/ui-style components.
// Built on @headlessui/react primitives + Tailwind CSS + cn() utility.
//
// Usage:
//   import { Button, Card, CardHeader, CardTitle } from '@/components/ui';
//   import { Badge } from '@/components/ui/badge';

// Layout
export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent } from './card';
export { Separator } from './separator';
export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
} from './table';

// Forms
export { Button, buttonVariants } from './button';
export type { ButtonProps } from './button';
export { Input } from './input';
export type { InputProps } from './input';
export { Label } from './label';
export type { LabelProps } from './label';
export { Textarea } from './textarea';
export type { TextareaProps } from './textarea';
export { Select } from './select';
export type { SelectOption } from './select';
export { Switch } from './switch';

// Feedback
export { Alert, AlertTitle, AlertDescription } from './alert';
export { Badge, badgeVariants } from './badge';
export type { BadgeProps } from './badge';
export { Progress } from './progress';
export { Skeleton } from './skeleton';
export { Tooltip } from './tooltip';

// Overlay
export {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from './dialog';
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from './dropdown-menu';

// Data display
export { Avatar, AvatarImage, AvatarFallback } from './avatar';

// Data table (requires @tanstack/react-table)
export { DataTable, DataTableColumnHeader } from './data-table';
export type { ColumnDef, SortingState, ColumnFiltersState, VisibilityState, Row, DataTableInstance } from './data-table';
export { DataTablePagination } from './data-table-pagination';

// Tabs
export { Tabs, TabsList, TabsTrigger, TabsContent, TabsPanels } from './tabs';
