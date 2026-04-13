import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  CalendarDaysIcon,
  PlusIcon,
  EnvelopeIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { superAdminService, type DemoBooking } from '../../services/superAdminService';
import { Button, useToast } from '../../components/common';
import { FormField } from '../../components/common/FormField';
import { useZodForm } from '../../hooks/useZodForm';
import { usePageTitle } from '../../hooks/usePageTitle';

// ── Zod Schemas ──────────────────────────────────────────────────────

const CreateBookingSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().min(1, 'Email is required').email('Enter a valid email'),
  company: z.string().optional().or(z.literal('')),
  phone: z.string().optional().or(z.literal('')),
  scheduled_at: z.string().min(1, 'Scheduled date/time is required'),
  notes: z.string().optional().or(z.literal('')),
});

type CreateBookingData = z.infer<typeof CreateBookingSchema>;

const SendEmailSchema = z.object({
  subject: z.string().min(1, 'Subject is required'),
  body: z.string().min(1, 'Body is required'),
});

type SendEmailData = z.infer<typeof SendEmailSchema>;

const STATUS_COLORS: Record<string, string> = {
  scheduled: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-slate-100 text-slate-500',
  no_show: 'bg-red-100 text-red-700',
};

const STATUS_OPTIONS = ['scheduled', 'completed', 'cancelled', 'no_show'] as const;

export const DemoBookingsPage: React.FC = () => {
  usePageTitle('Demo Bookings');
  const toast = useToast();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [emailTarget, setEmailTarget] = useState<DemoBooking | null>(null);

  const createForm = useZodForm({
    schema: CreateBookingSchema,
    defaultValues: { name: '', email: '', company: '', phone: '', scheduled_at: '', notes: '' },
  });

  const emailForm = useZodForm({
    schema: SendEmailSchema,
    defaultValues: { subject: '', body: '' },
  });

  const { data, isLoading } = useQuery({
    queryKey: ['demo-bookings', search, statusFilter],
    queryFn: () => superAdminService.listDemoBookings({ search: search || undefined, status: statusFilter || undefined }),
  });

  const createMut = useMutation({
    mutationFn: (d: CreateBookingData) => superAdminService.createDemoBooking({ ...d, scheduled_at: new Date(d.scheduled_at).toISOString() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['demo-bookings'] });
      toast.success('Booking Created', 'Demo booking has been added and follow-up email queued.');
      setShowCreate(false);
      createForm.reset();
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        Object.entries(detail).forEach(([field, messages]) => {
          if (field in CreateBookingSchema.shape) {
            createForm.setError(field as keyof CreateBookingData, {
              type: 'server',
              message: Array.isArray(messages) ? (messages as string[])[0] : String(messages),
            });
          }
        });
      }
      toast.error('Error', err?.response?.data?.error || 'Failed to create booking');
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<DemoBooking> }) => superAdminService.updateDemoBooking(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['demo-bookings'] });
      toast.success('Updated', 'Booking status updated.');
    },
    onError: () => toast.error('Error', 'Failed to update booking'),
  });

  const emailMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: SendEmailData }) => superAdminService.sendDemoBookingEmail(id, data),
    onSuccess: () => {
      toast.success('Email Sent', 'Email has been queued for delivery.');
      setEmailTarget(null);
      emailForm.reset();
    },
    onError: () => toast.error('Error', 'Failed to send email'),
  });

  const bookings = data?.results || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Demo Bookings</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">Track and manage demo call bookings</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-[13px] font-semibold text-white shadow-sm hover:bg-indigo-700 transition"
        >
          <PlusIcon className="h-4 w-4" />
          Add Booking
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name, email, or company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-200/80 rounded-xl text-[13px] focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 placeholder:text-slate-400"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-slate-200/80 rounded-xl text-[13px] focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
        >
          <option value="">All Statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
        </div>
      ) : bookings.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          <CalendarDaysIcon className="h-8 w-8 mx-auto mb-3 text-slate-200" />
          <p className="font-medium text-[13px]">No demo bookings yet</p>
          <p className="text-[13px] text-slate-400 mt-1">Bookings from Cal.com will appear here automatically.</p>
        </div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-2xl border border-slate-200/80 shadow-sm">
          <table className="min-w-full divide-y divide-slate-100/80">
            <thead className="bg-slate-50/60">
              <tr>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Name</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Email</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide hidden lg:table-cell">Company</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Scheduled</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Source</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-right text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/80">
              {bookings.map((b) => (
                <tr key={b.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3 text-[13px] font-medium text-slate-900">{b.name}</td>
                  <td className="px-4 py-3 text-[13px] text-slate-600">{b.email}</td>
                  <td className="px-4 py-3 text-[13px] text-slate-600 hidden lg:table-cell">{b.company || '—'}</td>
                  <td className="px-4 py-3 text-[13px] text-slate-600">
                    {b.scheduled_at ? new Date(b.scheduled_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                  </td>
                  <td className="px-4 py-3 text-[13px]">
                    <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold ${b.source === 'cal_webhook' ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-600'}`}>
                      {b.source === 'cal_webhook' ? 'Cal.com' : 'Manual'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[13px]">
                    <select
                      value={b.status}
                      onChange={(e) => updateMut.mutate({ id: b.id, data: { status: e.target.value as DemoBooking['status'] } })}
                      className={`px-2 py-1 rounded text-[10px] font-semibold border-0 cursor-pointer ${STATUS_COLORS[b.status] || 'bg-slate-100'}`}
                    >
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-[13px] text-right">
                    <button
                      onClick={() => { setEmailTarget(b); emailForm.reset(); }}
                      className="text-indigo-600 hover:text-indigo-800 p-1"
                      title="Send email"
                    >
                      <EnvelopeIcon className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Booking Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-[2px]">
          <form
            onSubmit={createForm.handleSubmit((data) => createMut.mutate(data))}
            noValidate
            className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[15px] font-bold text-slate-900">Add Demo Booking</h2>
              <button type="button" onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600"><XMarkIcon className="h-5 w-5" /></button>
            </div>
            <div className="space-y-3">
              <FormField control={createForm.control} name="name" label="Name *" />
              <FormField control={createForm.control} name="email" label="Email *" type="email" />
              <div className="grid grid-cols-2 gap-3">
                <FormField control={createForm.control} name="company" label="Company" />
                <FormField control={createForm.control} name="phone" label="Phone" />
              </div>
              <Controller
                control={createForm.control}
                name="scheduled_at"
                render={({ field, fieldState }) => (
                  <div>
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">Scheduled Date/Time *</label>
                    <input
                      type="datetime-local"
                      value={field.value}
                      onChange={field.onChange}
                      onBlur={field.onBlur}
                      className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-[13px] focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
                    />
                    {fieldState.error && (
                      <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />
              <Controller
                control={createForm.control}
                name="notes"
                render={({ field }) => (
                  <div>
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">Notes</label>
                    <textarea rows={2} value={field.value} onChange={field.onChange} onBlur={field.onBlur} className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-[13px] focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400" />
                  </div>
                )}
              />
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-[13px] font-semibold text-slate-700 border border-slate-200/80 rounded-lg shadow-sm hover:bg-slate-50">Cancel</button>
              <button
                type="submit"
                disabled={createMut.isPending}
                className="px-4 py-2 text-[13px] font-semibold text-white bg-indigo-600 rounded-lg shadow-sm hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMut.isPending ? 'Creating...' : 'Create Booking'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Send Email Modal */}
      {emailTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-[2px]">
          <form
            onSubmit={emailForm.handleSubmit((data) => emailMut.mutate({ id: emailTarget.id, data }))}
            noValidate
            className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[15px] font-bold text-slate-900">Email {emailTarget.name}</h2>
              <button type="button" onClick={() => setEmailTarget(null)} className="text-slate-400 hover:text-slate-600"><XMarkIcon className="h-5 w-5" /></button>
            </div>
            <p className="text-[13px] text-slate-500 mb-3">To: {emailTarget.email}</p>
            <div className="space-y-3">
              <FormField control={emailForm.control} name="subject" label="Subject *" />
              <Controller
                control={emailForm.control}
                name="body"
                render={({ field, fieldState }) => (
                  <div>
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">Body *</label>
                    <textarea rows={4} value={field.value} onChange={field.onChange} onBlur={field.onBlur} className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-[13px] focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400" />
                    {fieldState.error && (
                      <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <button type="button" onClick={() => setEmailTarget(null)} className="px-4 py-2 text-[13px] font-semibold text-slate-700 border border-slate-200/80 rounded-lg shadow-sm hover:bg-slate-50">Cancel</button>
              <button
                type="submit"
                disabled={emailMut.isPending}
                className="px-4 py-2 text-[13px] font-semibold text-white bg-indigo-600 rounded-lg shadow-sm hover:bg-indigo-700 disabled:opacity-50"
              >
                {emailMut.isPending ? 'Sending...' : 'Send Email'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
