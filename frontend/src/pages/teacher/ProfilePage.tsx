// src/pages/teacher/ProfilePage.tsx

import React, { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { useAuthStore } from '../../stores/authStore';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { FormField } from '../../components/common/FormField';
import { useToast } from '../../components/common';
import { useZodForm } from '../../hooks/useZodForm';
import api from '../../config/api';
import { useGuidedTour } from '../../components/tour';
import { teacherService } from '../../services/teacherService';
import { DailyQuestCard } from '../../components/teacher/dashboard/DailyQuestCard';
import { FishEvolutionWidget } from '../../components/teacher/dashboard/FishEvolutionWidget';
import {
  UserCircleIcon,
  EnvelopeIcon,
  BriefcaseIcon,
  AcademicCapIcon,
  KeyIcon,
  BellIcon,
  CameraIcon,
  BookOpenIcon,
  IdentificationIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Password change schema ───────────────────────────────────────────────────

const ChangePasswordSchema = z
  .object({
    current_password: z.string().min(1, 'Current password is required'),
    new_password: z
      .string()
      .min(8, 'New password must be at least 8 characters')
      .max(128),
    confirm_password: z.string().min(1, 'Please confirm your new password'),
  })
  .refine((d: { new_password: string; confirm_password: string }) => d.new_password === d.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  });

type ChangePasswordData = z.infer<typeof ChangePasswordSchema>;

const COMMON_SUBJECTS = [
  'Mathematics', 'Physics', 'Chemistry', 'Biology', 'English',
  'Hindi', 'Sanskrit', 'Social Science', 'History', 'Geography',
  'Political Science', 'Economics', 'Computer Science', 'Information Technology',
  'Physical Education', 'Art & Craft', 'Music', 'Environmental Science',
  'Accountancy', 'Business Studies', 'Home Science', 'Psychology',
];

const COMMON_GRADES = [
  'Nursery', 'LKG', 'UKG',
  'Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5',
  'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10',
  'Class 11', 'Class 12',
];

const DESIGNATIONS = [
  'PRT (Primary Teacher)', 'TGT (Trained Graduate Teacher)',
  'PGT (Post Graduate Teacher)', 'Head of Department',
  'Vice Principal', 'Coordinator', 'Counsellor',
  'Librarian', 'Lab Assistant', 'Sports Coach',
];

const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');

type ProfileSection = 'profile' | 'password' | 'notifications' | 'achievements';

export const ProfilePage: React.FC = () => {
  usePageTitle('Profile');
  const toast = useToast();
  const queryClient = useQueryClient();
  const { startTour } = useGuidedTour();
  const { user, setUser } = useAuthStore();
  const [activeSection, setActiveSection] = useState<ProfileSection>('profile');
  const [isSaving, setIsSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [profileForm, setProfileForm] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    email: user?.email || '',
    department: user?.department || '',
    employee_id: user?.employee_id || '',
    designation: user?.designation || '',
    bio: user?.bio || '',
    subjects: user?.subjects || [],
    grades: user?.grades || [],
  });

  const [profilePicPreview, setProfilePicPreview] = useState<string | null>(
    user?.profile_picture_url || user?.profile_picture || null,
  );
  const [profilePicFile, setProfilePicFile] = useState<File | null>(null);

  // Password change form — uses RHF + Zod for strict validation
  const passwordForm = useZodForm({
    schema: ChangePasswordSchema,
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  });

  const [notifications, setNotifications] = useState({
    email_courses: true,
    email_assignments: true,
    email_reminders: true,
    email_announcements: true,
  });

  // Fetch notification preferences from API
  const { data: prefsData } = useQuery({
    queryKey: ['notificationPreferences'],
    queryFn: async () => {
      const res = await api.get('/users/auth/preferences/');
      return res.data;
    },
  });

  useEffect(() => {
    if (prefsData && typeof prefsData === 'object') {
      setNotifications((prev) => ({ ...prev, ...prefsData }));
    }
  }, [prefsData]);

  const { data: gamification, isLoading: achievementsLoading } = useQuery({
    queryKey: ['teacherGamification'],
    queryFn: teacherService.getGamificationSummary,
    enabled: activeSection === 'achievements',
  });

  const claimQuestMutation = useMutation({
    mutationFn: (questKey: string) => teacherService.claimQuestReward(questKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teacherGamification'] });
      queryClient.invalidateQueries({ queryKey: ['teacherDashboard'] });
      toast.success('Reward claimed', 'Your daily quest points were added.');
    },
    onError: () => {
      toast.error('Unable to claim', 'The reward is not claimable right now.');
    },
  });

  const handlePicChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setProfilePicFile(file);
      const reader = new FileReader();
      reader.onloadend = () => setProfilePicPreview(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const toggleSubject = (subject: string) => {
    setProfileForm((prev) => ({
      ...prev,
      subjects: prev.subjects.includes(subject)
        ? prev.subjects.filter((value: string) => value !== subject)
        : [...prev.subjects, subject],
    }));
  };

  const toggleGrade = (grade: string) => {
    setProfileForm((prev) => ({
      ...prev,
      grades: prev.grades.includes(grade)
        ? prev.grades.filter((value: string) => value !== grade)
        : [...prev.grades, grade],
    }));
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const fd = new FormData();
      fd.append('first_name', profileForm.first_name);
      fd.append('last_name', profileForm.last_name);
      fd.append('department', profileForm.department);
      fd.append('designation', profileForm.designation);
      fd.append('bio', profileForm.bio);
      fd.append('subjects', JSON.stringify(profileForm.subjects));
      fd.append('grades', JSON.stringify(profileForm.grades));
      if (profilePicFile) {
        fd.append('profile_picture', profilePicFile);
      }
      const res = await api.patch('/users/auth/me/', fd);
      setUser(res.data);
      toast.success('Profile updated', 'Your profile has been saved successfully.');
    } catch {
      toast.error('Failed', 'Could not save profile.');
    } finally {
      setIsSaving(false);
    }
  };

  const handlePasswordSubmit = passwordForm.handleSubmit(
    async (data: ChangePasswordData) => {
      setIsSaving(true);
      try {
        const { authService } = await import('../../services/authService');
        await authService.changePassword(data.current_password, data.new_password);
        passwordForm.reset();
        toast.success('Password updated', 'Your password has been changed.');
      } catch {
        toast.error('Failed', 'Could not change password. Check your current password.');
        passwordForm.setError('current_password', {
          type: 'server',
          message: 'Current password is incorrect',
        });
      } finally {
        setIsSaving(false);
      }
    },
  );

  const handleNotificationsSave = async () => {
    setIsSaving(true);
    try {
      await api.patch('/users/auth/preferences/', notifications);
      toast.success('Preferences saved', 'Your notification preferences have been updated.');
    } catch {
      toast.error('Failed', 'Could not save preferences.');
    } finally {
      setIsSaving(false);
    }
  };

  const resolveAvatar = () => {
    if (profilePicPreview) {
      if (profilePicPreview.startsWith('data:') || profilePicPreview.startsWith('http')) return profilePicPreview;
      return `${backendOrigin}${profilePicPreview.startsWith('/') ? '' : '/'}${profilePicPreview}`;
    }
    return null;
  };

  const avatarUrl = resolveAvatar();

  const sections = [
    { id: 'profile', label: 'Profile', icon: UserCircleIcon },
    { id: 'password', label: 'Password', icon: KeyIcon },
    { id: 'notifications', label: 'Notifications', icon: BellIcon },
    { id: 'achievements', label: 'Achievements', icon: SparklesIcon },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Profile Settings</h1>
          <p className="mt-1 text-[13px] text-slate-500">Manage your account settings, preferences, and growth milestones</p>
        </div>
        <Button
          type="button"
          variant="outline"
          className="w-full sm:w-auto"
          onClick={startTour}
          data-tour="teacher-profile-tour-replay"
        >
          Start Tour
        </Button>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="lg:w-72 flex-shrink-0">
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
            <div className="p-6 text-center border-b border-slate-200/80 relative">
              <div className="relative inline-block">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="" className="h-24 w-24 mx-auto rounded-full object-cover border-4 border-orange-100" />
                ) : (
                  <div className="h-24 w-24 mx-auto rounded-full bg-orange-100 flex items-center justify-center border-4 border-orange-50">
                    <span className="text-3xl font-semibold text-orange-700">
                      {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
                    </span>
                  </div>
                )}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute bottom-0 right-0 h-8 w-8 bg-tp-accent text-white rounded-full flex items-center justify-center shadow-lg hover:bg-orange-600 transition-colors"
                  title="Change photo"
                >
                  <CameraIcon className="h-4 w-4" />
                </button>
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handlePicChange} className="hidden" />
              </div>
              <h3 className="font-semibold text-slate-900 mt-3">{user?.first_name} {user?.last_name}</h3>
              <p className="text-[13px] text-tp-accent font-medium">{profileForm.designation || user?.role?.replace('_', ' ')}</p>
              {profileForm.employee_id && (
                <p className="text-xs text-slate-400 mt-1">ID: {profileForm.employee_id}</p>
              )}
            </div>

            <nav data-tour="teacher-profile-sections" className="flex gap-1 overflow-x-auto p-2 lg:block lg:space-y-1">
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id as ProfileSection)}
                  className={`flex flex-shrink-0 items-center rounded-lg px-4 py-3 text-[13px] font-medium transition-colors lg:w-full ${
                    activeSection === section.id
                      ? 'bg-orange-50 text-tp-accent'
                      : 'text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <section.icon className="h-5 w-5 mr-3" />
                  <span className="whitespace-nowrap">{section.label}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>

        <div className="flex-1">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-4 sm:p-6">
            {activeSection === 'profile' && (
              <form data-tour="teacher-profile-form" onSubmit={handleProfileSubmit}>
                <h2 className="text-[15px] font-semibold text-slate-900 mb-6">Profile Information</h2>

                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <Input
                    label="First Name"
                    value={profileForm.first_name}
                    onChange={(e) => setProfileForm({ ...profileForm, first_name: e.target.value })}
                    leftIcon={<UserCircleIcon className="h-5 w-5" />}
                  />
                  <Input
                    label="Last Name"
                    value={profileForm.last_name}
                    onChange={(e) => setProfileForm({ ...profileForm, last_name: e.target.value })}
                    leftIcon={<UserCircleIcon className="h-5 w-5" />}
                  />
                  <Input
                    label="Email"
                    type="email"
                    value={profileForm.email}
                    leftIcon={<EnvelopeIcon className="h-5 w-5" />}
                    disabled
                    helperText="Contact admin to change email"
                  />
                  <Input
                    label="Teacher ID"
                    value={profileForm.employee_id}
                    leftIcon={<IdentificationIcon className="h-5 w-5" />}
                    disabled
                    helperText="Assigned by school administration"
                  />

                  <div>
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">Designation</label>
                    <select
                      value={profileForm.designation}
                      onChange={(e) => setProfileForm({ ...profileForm, designation: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-200/80 rounded-xl focus:ring-2 focus:ring-orange-500/20 focus:border-orange-400"
                    >
                      <option value="">Select designation...</option>
                      {DESIGNATIONS.map((designation) => <option key={designation} value={designation}>{designation}</option>)}
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  <Input
                    label="Department"
                    value={profileForm.department}
                    onChange={(e) => setProfileForm({ ...profileForm, department: e.target.value })}
                    leftIcon={<BriefcaseIcon className="h-5 w-5" />}
                    placeholder="e.g. Science, Languages"
                  />

                  <div className="sm:col-span-2">
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">About Me</label>
                    <textarea
                      value={profileForm.bio}
                      onChange={(e) => setProfileForm({ ...profileForm, bio: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 border border-slate-200/80 rounded-xl focus:ring-2 focus:ring-orange-500/20 focus:border-orange-400"
                      placeholder="Tell us about yourself, your teaching philosophy, experience..."
                    />
                  </div>
                </div>

                <div className="mt-6">
                  <label className="flex items-center gap-2 text-[13px] font-medium text-slate-700 mb-2">
                    <BookOpenIcon className="h-4 w-4" /> Subjects I Teach
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {COMMON_SUBJECTS.map((subject) => (
                      <button
                        key={subject}
                        type="button"
                        onClick={() => toggleSubject(subject)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                          profileForm.subjects.includes(subject)
                            ? 'bg-orange-100 border-orange-300 text-orange-800'
                            : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        {subject}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-5">
                  <label className="flex items-center gap-2 text-[13px] font-medium text-slate-700 mb-2">
                    <AcademicCapIcon className="h-4 w-4" /> Classes / Grades
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {COMMON_GRADES.map((grade) => (
                      <button
                        key={grade}
                        type="button"
                        onClick={() => toggleGrade(grade)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                          profileForm.grades.includes(grade)
                            ? 'bg-blue-100 border-blue-300 text-blue-800'
                            : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        {grade}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-6 flex justify-end">
                  <Button type="submit" loading={isSaving} className="w-full bg-tp-accent hover:bg-orange-600 sm:w-auto">
                    Save Changes
                  </Button>
                </div>
              </form>
            )}

            {activeSection === 'password' && (
              <form onSubmit={handlePasswordSubmit} noValidate>
                <h2 className="text-[15px] font-semibold text-slate-900 mb-6">Change Password</h2>
                <div className="max-w-md space-y-6">
                  <FormField
                    control={passwordForm.control}
                    name="current_password"
                    label="Current Password"
                    type="password"
                    autoComplete="current-password"
                    leftIcon={<KeyIcon className="h-5 w-5" />}
                  />
                  <FormField
                    control={passwordForm.control}
                    name="new_password"
                    label="New Password"
                    type="password"
                    autoComplete="new-password"
                    leftIcon={<KeyIcon className="h-5 w-5" />}
                    helperText="Must be at least 8 characters"
                  />
                  <FormField
                    control={passwordForm.control}
                    name="confirm_password"
                    label="Confirm New Password"
                    type="password"
                    autoComplete="new-password"
                    leftIcon={<KeyIcon className="h-5 w-5" />}
                  />
                </div>
                <div className="mt-6 flex justify-end">
                  <Button
                    type="submit"
                    loading={isSaving || passwordForm.formState.isSubmitting}
                    className="w-full bg-tp-accent hover:bg-orange-600 sm:w-auto"
                  >
                    Update Password
                  </Button>
                </div>
              </form>
            )}

            {activeSection === 'notifications' && (
              <div>
                <h2 className="text-[15px] font-semibold text-slate-900 mb-6">Notification Preferences</h2>
                <div className="space-y-4">
                  {[
                    { key: 'email_courses', title: 'Course Updates', desc: 'Get notified when courses are updated' },
                    { key: 'email_assignments', title: 'Assignment Reminders', desc: 'Receive reminders for pending assignments' },
                    { key: 'email_reminders', title: 'Reminder Alerts', desc: 'Get alerts for upcoming reminders' },
                    { key: 'email_announcements', title: 'Announcements', desc: 'Receive announcement notifications' },
                  ].map((item) => (
                    <div key={item.key} className="flex flex-col gap-3 border-b border-slate-200/80 py-3 sm:flex-row sm:items-center sm:justify-between last:border-0">
                      <div>
                        <p className="text-[13px] font-medium text-slate-900">{item.title}</p>
                        <p className="text-[13px] text-slate-500">{item.desc}</p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={notifications[item.key as keyof typeof notifications]}
                          onChange={(e) => setNotifications({ ...notifications, [item.key]: e.target.checked })}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-orange-300/50 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-tp-accent"></div>
                      </label>
                    </div>
                  ))}
                </div>
                <div className="mt-6 flex justify-end">
                  <Button onClick={handleNotificationsSave} loading={isSaving} className="w-full bg-tp-accent hover:bg-orange-600 sm:w-auto">
                    Save Preferences
                  </Button>
                </div>
              </div>
            )}

            {activeSection === 'achievements' && (
              <div className="space-y-5">
                {achievementsLoading ? (
                  <div className="space-y-3">
                    <div className="h-28 animate-pulse rounded-xl bg-slate-100" />
                    <div className="h-72 animate-pulse rounded-xl bg-slate-100" />
                    <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
                  </div>
                ) : gamification ? (
                  <>
                    <section className="rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50 to-sky-50 p-5">
                      <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">Live Journey Sync</p>
                      <h2 className="mt-1 text-2xl font-bold text-slate-900">Fish + Puddle State</h2>
                      <p className="mt-2 text-sm text-slate-600">
                        Points synced: <span className="font-semibold text-slate-800">{gamification.points_total}</span>
                      </p>
                      <p className="text-sm text-slate-500">
                        Only your active state is highlighted. Other states stay muted until reached.
                      </p>
                    </section>

                    <FishEvolutionWidget pointsTotal={gamification.points_total} />

                    <DailyQuestCard
                      quest={gamification.quest}
                      claiming={claimQuestMutation.isPending}
                      onClaim={() => claimQuestMutation.mutate(gamification.quest.key)}
                    />
                  </>
                ) : (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-600">
                    Could not load achievements right now.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
