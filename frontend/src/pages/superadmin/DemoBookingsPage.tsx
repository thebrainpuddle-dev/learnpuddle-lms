import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CalendarDaysIcon,
  PlusIcon,
  EnvelopeIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
  PhoneIcon,
  BuildingOfficeIcon,
} from '@heroicons/react/24/outline';
import { superAdminService, type DemoBooking } from '../../services/superAdminService';
import { useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';

const STATUS_COLORS: Record<string, string> = {
  scheduled: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-500',
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
  const [createForm, setCreateForm] = useState({ name: '', email: '', company: '', phone: '', scheduled_at: '', notes: '' });
  const [emailForm, setEmailForm] = useState({ subject: '', body: '' });

  const { data, isLoading } = useQuery({
    queryKey: ['demo-bookings', search, statusFilter],
    queryFn: () => superAdminService.listDemoBookings({ search: search || undefined, status: statusFilter || undefined }),
  });

  const createMut = useMutation({
    mutationFn: (d: typeof createForm) => superAdminService.createDemoBooking(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['demo-bookings'] });
      toast.success('Booking Created', 'Demo booking has been added and follow-up email queued.');
      setShowCreate(false);
      setCreateForm({ name: '', email: '', company: '', phone: '', scheduled_at: '', notes: '' });
    },
    onError: (err: any) => toast.error('Error', err?.response?.data?.error || 'Failed to create booking'),
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
    mutationFn: ({ id, data }: { id: string; data: { subject: string; body: string } }) => superAdminService.sendDemoBookingEmail(id, data),
    onSuccess: () => {
      toast.success('Email Sent', 'Email has been queued for delivery.');
      setEmailTarget(null);
      setEmailForm({ subject: '', body: '' });
    },
    onError: () => toast.error('Error', 'Failed to send email'),
  });

  const bookings = data?.results || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Demo Bookings</h1>
          <p className="text-sm text-gray-500 mt-1">Track and manage demo call bookings</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-indigo-700 transition"
        >
          <PlusIcon className="h-4 w-4" />
          Add Booking
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search by name, email, or company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
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
          {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-gray-100 rounded-lg" />)}
        </div>
      ) : bookings.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <CalendarDaysIcon className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No demo bookings yet</p>
          <p className="text-sm mt-1">Bookings from Cal.com will appear here automatically.</p>
        </div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase hidden lg:table-cell">Company</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scheduled</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {bookings.map((b) => (
                <tr key={b.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{b.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{b.email}</td>
                  <td className="px-4 py-3 text-sm text-gray-600 hidden lg:table-cell">{b.company || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {b.scheduled_at ? new Date(b.scheduled_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${b.source === 'cal_webhook' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                      {b.source === 'cal_webhook' ? 'Cal.com' : 'Manual'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <select
                      value={b.status}
                      onChange={(e) => updateMut.mutate({ id: b.id, data: { status: e.target.value as DemoBooking['status'] } })}
                      className={`px-2 py-1 rounded text-xs font-medium border-0 cursor-pointer ${STATUS_COLORS[b.status] || 'bg-gray-100'}`}
                    >
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-sm text-right">
                    <button
                      onClick={() => { setEmailTarget(b); setEmailForm({ subject: '', body: '' }); }}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Add Demo Booking</h2>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="h-5 w-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
                <input type="text" value={createForm.name} onChange={(e) => setCreateForm(p => ({ ...p, name: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                <input type="email" value={createForm.email} onChange={(e) => setCreateForm(p => ({ ...p, email: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Company</label>
                  <input type="text" value={createForm.company} onChange={(e) => setCreateForm(p => ({ ...p, company: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                  <input type="text" value={createForm.phone} onChange={(e) => setCreateForm(p => ({ ...p, phone: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Scheduled Date/Time *</label>
                <input type="datetime-local" value={createForm.scheduled_at} onChange={(e) => setCreateForm(p => ({ ...p, scheduled_at: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                <textarea rows={2} value={createForm.notes} onChange={(e) => setCreateForm(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
              <button
                onClick={() => {
                  if (!createForm.name || !createForm.email || !createForm.scheduled_at) { toast.error('Missing Fields', 'Name, email, and date are required.'); return; }
                  createMut.mutate({ ...createForm, scheduled_at: new Date(createForm.scheduled_at).toISOString() });
                }}
                disabled={createMut.isPending}
                className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMut.isPending ? 'Creating...' : 'Create Booking'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Send Email Modal */}
      {emailTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Email {emailTarget.name}</h2>
              <button onClick={() => setEmailTarget(null)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="h-5 w-5" /></button>
            </div>
            <p className="text-sm text-gray-500 mb-3">To: {emailTarget.email}</p>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Subject *</label>
                <input type="text" value={emailForm.subject} onChange={(e) => setEmailForm(p => ({ ...p, subject: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Body *</label>
                <textarea rows={4} value={emailForm.body} onChange={(e) => setEmailForm(p => ({ ...p, body: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <button onClick={() => setEmailTarget(null)} className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
              <button
                onClick={() => {
                  if (!emailForm.subject || !emailForm.body) { toast.error('Missing Fields', 'Subject and body are required.'); return; }
                  emailMut.mutate({ id: emailTarget.id, data: emailForm });
                }}
                disabled={emailMut.isPending}
                className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {emailMut.isPending ? 'Sending...' : 'Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
