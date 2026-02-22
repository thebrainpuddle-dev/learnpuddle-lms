// src/pages/teacher/ProfilePage.tsx

import React, { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import api from '../../config/api';
import { useGuidedTour } from '../../components/tour';
import { teacherService } from '../../services/teacherService';
import { BadgeShowcase } from '../../components/teacher/dashboard/BadgeShowcase';
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

  const [passwordForm, setPasswordForm] = useState({
    current_password: '', new_password: '', confirm_password: '',
  });

  const [notifications, setNotifications] = useState({
    email_course_updates: true,
    email_assignment_reminders: true,
    email_deadline_alerts: true,
    browser_notifications: false,
  });

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

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      toast.error('Passwords do not match', 'Please ensure both passwords are the same.');
      return;
    }
    setIsSaving(true);
    try {
      const { authService } = await import('../../services/authService');
      await authService.changePassword(passwordForm.current_password, passwordForm.new_password);
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
      toast.success('Password updated', 'Your password has been changed.');
    } catch {
      toast.error('Failed', 'Could not change password. Check your current password.');
    } finally {
      setIsSaving(false);
    }
  };

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
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Profile Settings</h1>
          <p className="mt-1 text-gray-500">Manage your account settings, preferences, and growth milestones</p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={startTour}
          data-tour="teacher-profile-tour-replay"
        >
          Start Tour
        </Button>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="lg:w-72 flex-shrink-0">
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="p-6 text-center border-b border-gray-100 relative">
              <div className="relative inline-block">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="" className="h-24 w-24 mx-auto rounded-full object-cover border-4 border-emerald-100" />
                ) : (
                  <div className="h-24 w-24 mx-auto rounded-full bg-emerald-100 flex items-center justify-center border-4 border-emerald-50">
                    <span className="text-3xl font-semibold text-emerald-700">
                      {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
                    </span>
                  </div>
                )}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute bottom-0 right-0 h-8 w-8 bg-emerald-600 text-white rounded-full flex items-center justify-center shadow-lg hover:bg-emerald-700 transition-colors"
                  title="Change photo"
                >
                  <CameraIcon className="h-4 w-4" />
                </button>
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handlePicChange} className="hidden" />
              </div>
              <h3 className="font-semibold text-gray-900 mt-3">{user?.first_name} {user?.last_name}</h3>
              <p className="text-sm text-emerald-600 font-medium">{profileForm.designation || user?.role?.replace('_', ' ')}</p>
              {profileForm.employee_id && (
                <p className="text-xs text-gray-400 mt-1">ID: {profileForm.employee_id}</p>
              )}
            </div>

            <nav data-tour="teacher-profile-sections" className="p-2">
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id as ProfileSection)}
                  className={`w-full flex items-center px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                    activeSection === section.id
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  <section.icon className="h-5 w-5 mr-3" />
                  {section.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        <div className="flex-1">
          <div className="bg-white rounded-xl border border-gray-100 p-6">
            {activeSection === 'profile' && (
              <form data-tour="teacher-profile-form" onSubmit={handleProfileSubmit}>
                <h2 className="text-lg font-semibold text-gray-900 mb-6">Profile Information</h2>

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
                    <label className="block text-sm font-medium text-gray-700 mb-1">Designation</label>
                    <select
                      value={profileForm.designation}
                      onChange={(e) => setProfileForm({ ...profileForm, designation: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
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
                    <label className="block text-sm font-medium text-gray-700 mb-1">About Me</label>
                    <textarea
                      value={profileForm.bio}
                      onChange={(e) => setProfileForm({ ...profileForm, bio: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
                      placeholder="Tell us about yourself, your teaching philosophy, experience..."
                    />
                  </div>
                </div>

                <div className="mt-6">
                  <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
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
                            ? 'bg-emerald-100 border-emerald-300 text-emerald-800'
                            : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                        }`}
                      >
                        {subject}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-5">
                  <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
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
                            : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                        }`}
                      >
                        {grade}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-6 flex justify-end">
                  <Button type="submit" loading={isSaving} className="bg-emerald-600 hover:bg-emerald-700">
                    Save Changes
                  </Button>
                </div>
              </form>
            )}

            {activeSection === 'password' && (
              <form onSubmit={handlePasswordSubmit}>
                <h2 className="text-lg font-semibold text-gray-900 mb-6">Change Password</h2>
                <div className="max-w-md space-y-6">
                  <Input label="Current Password" type="password" value={passwordForm.current_password} onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })} leftIcon={<KeyIcon className="h-5 w-5" />} required />
                  <Input label="New Password" type="password" value={passwordForm.new_password} onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })} leftIcon={<KeyIcon className="h-5 w-5" />} helperText="Must be at least 8 characters" required />
                  <Input label="Confirm New Password" type="password" value={passwordForm.confirm_password} onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })} leftIcon={<KeyIcon className="h-5 w-5" />} required />
                </div>
                <div className="mt-6 flex justify-end">
                  <Button type="submit" loading={isSaving} className="bg-emerald-600 hover:bg-emerald-700">Update Password</Button>
                </div>
              </form>
            )}

            {activeSection === 'notifications' && (
              <div>
                <h2 className="text-lg font-semibold text-gray-900 mb-6">Notification Preferences</h2>
                <div className="space-y-4">
                  {[
                    { key: 'email_course_updates', title: 'Course Updates', desc: 'Get notified when courses are updated' },
                    { key: 'email_assignment_reminders', title: 'Assignment Reminders', desc: 'Receive reminders for pending assignments' },
                    { key: 'email_deadline_alerts', title: 'Deadline Alerts', desc: 'Get alerts before deadlines approach' },
                    { key: 'browser_notifications', title: 'Browser Notifications', desc: 'Enable desktop push notifications' },
                  ].map((item) => (
                    <div key={item.key} className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
                      <div>
                        <p className="font-medium text-gray-900">{item.title}</p>
                        <p className="text-sm text-gray-500">{item.desc}</p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={notifications[item.key as keyof typeof notifications]}
                          onChange={(e) => setNotifications({ ...notifications, [item.key]: e.target.checked })}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                      </label>
                    </div>
                  ))}
                </div>
                <div className="mt-6 flex justify-end">
                  <Button onClick={handleNotificationsSave} loading={isSaving} className="bg-emerald-600 hover:bg-emerald-700">
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
                    <section className="rounded-xl border border-violet-100 bg-gradient-to-r from-violet-50 to-indigo-50 p-5">
                      <p className="text-xs font-semibold uppercase tracking-wide text-violet-600">Current Level</p>
                      <h2 className="mt-1 text-2xl font-bold text-slate-900">
                        Level {gamification.badge_current.level}: {gamification.badge_current.name}
                      </h2>
                      <p className="text-sm text-slate-600">{gamification.badge_current.ripple_range}</p>
                      <p className="mt-3 text-sm font-semibold text-violet-700">Total Ripples: {gamification.points_total}</p>
                    </section>

                    <FishEvolutionWidget pointsTotal={gamification.points_total} />

                    <DailyQuestCard
                      quest={gamification.quest}
                      claiming={claimQuestMutation.isPending}
                      onClaim={() => claimQuestMutation.mutate(gamification.quest.key)}
                    />

                    <BadgeShowcase badges={gamification.badges} currentLevel={gamification.badge_current.level} />
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
