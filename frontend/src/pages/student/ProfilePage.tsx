// src/pages/student/ProfilePage.tsx

import React, { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import api from '../../config/api';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  UserCircleIcon,
  EnvelopeIcon,
  AcademicCapIcon,
  IdentificationIcon,
  CalendarDaysIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';

const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');

export const ProfilePage: React.FC = () => {
  usePageTitle('Profile');
  const toast = useToast();
  const { user, setUser } = useAuthStore();
  const [isSaving, setIsSaving] = useState(false);

  // Cast user to access student-specific fields from the backend response
  const studentUser = user as Record<string, any> | null;

  const [profileForm, setProfileForm] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    bio: studentUser?.bio || '',
  });

  const resolveAvatar = () => {
    const pic = studentUser?.profile_picture_url || studentUser?.profile_picture;
    if (!pic) return null;
    if (pic.startsWith('data:') || pic.startsWith('http')) return pic;
    return `${backendOrigin}${pic.startsWith('/') ? '' : '/'}${pic}`;
  };

  const avatarUrl = resolveAvatar();

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const res = await api.patch('/users/auth/me/', {
        first_name: profileForm.first_name,
        last_name: profileForm.last_name,
        bio: profileForm.bio,
      });
      setUser(res.data);
      toast.success('Profile updated', 'Your profile has been saved successfully.');
    } catch {
      toast.error('Failed', 'Could not save profile.');
    } finally {
      setIsSaving(false);
    }
  };

  const formatDate = (dateStr: string | undefined | null) => {
    if (!dateStr) return 'N/A';
    try {
      return new Date(dateStr).toLocaleDateString('en-IN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  // Read-only detail items for the Student Details card
  const studentDetails = [
    {
      icon: IdentificationIcon,
      label: 'Student ID',
      value: studentUser?.student_id || 'Not assigned',
    },
    {
      icon: AcademicCapIcon,
      label: 'Grade',
      value: user?.grade_name || studentUser?.grade_level || 'Not assigned',
    },
    {
      icon: UsersIcon,
      label: 'Section',
      value: user?.section_name || studentUser?.section || 'Not assigned',
    },
    {
      icon: EnvelopeIcon,
      label: 'Parent Email',
      value: studentUser?.parent_email || 'Not provided',
    },
    {
      icon: CalendarDaysIcon,
      label: 'Enrollment Date',
      value: formatDate(studentUser?.enrollment_date),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">My Profile</h1>
        <p className="mt-1 text-[13px] text-slate-500">
          View your student details and manage your personal information
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar — Avatar + Account Info */}
        <div className="lg:w-80 flex-shrink-0 space-y-6">
          {/* Avatar Card */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
            <div className="bg-gradient-to-br from-indigo-500 to-indigo-600 h-24" />
            <div className="px-6 pb-6 -mt-12 text-center">
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt="Profile"
                  className="h-24 w-24 mx-auto rounded-full object-cover border-4 border-white shadow-md"
                />
              ) : (
                <div className="h-24 w-24 mx-auto rounded-full bg-indigo-100 flex items-center justify-center border-4 border-white shadow-md">
                  <span className="text-3xl font-semibold text-indigo-700">
                    {user?.first_name?.charAt(0)}
                    {user?.last_name?.charAt(0)}
                  </span>
                </div>
              )}
              <h3 className="font-semibold text-slate-900 mt-3 text-lg">
                {user?.first_name} {user?.last_name}
              </h3>
              <p className="text-[13px] text-indigo-600 font-medium mt-0.5">Student</p>
              {studentUser?.student_id && (
                <p className="text-xs text-slate-400 mt-1">ID: {studentUser.student_id}</p>
              )}
            </div>
          </div>

          {/* Account Card */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5">
            <h3 className="text-[13px] font-semibold text-slate-900 uppercase tracking-wider mb-4">
              Account
            </h3>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="flex-shrink-0 h-9 w-9 rounded-lg bg-slate-50 flex items-center justify-center">
                  <EnvelopeIcon className="h-4 w-4 text-slate-500" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] text-slate-400 font-medium">Email</p>
                  <p className="text-[13px] text-slate-700 truncate">{user?.email || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex-shrink-0 h-9 w-9 rounded-lg bg-slate-50 flex items-center justify-center">
                  <UserCircleIcon className="h-4 w-4 text-slate-500" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] text-slate-400 font-medium">Role</p>
                  <p className="text-[13px] text-slate-700">Student</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 space-y-6">
          {/* Personal Information — Editable */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5 sm:p-6">
            <h2 className="text-[15px] font-semibold text-slate-900 mb-1">Personal Information</h2>
            <p className="text-[13px] text-slate-500 mb-6">
              Update your name and bio. Other details are managed by your school.
            </p>

            <form onSubmit={handleProfileSubmit}>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Input
                  label="First Name"
                  value={profileForm.first_name}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, first_name: e.target.value })
                  }
                  leftIcon={<UserCircleIcon className="h-5 w-5" />}
                />
                <Input
                  label="Last Name"
                  value={profileForm.last_name}
                  onChange={(e) =>
                    setProfileForm({ ...profileForm, last_name: e.target.value })
                  }
                  leftIcon={<UserCircleIcon className="h-5 w-5" />}
                />

                <div className="sm:col-span-2">
                  <label className="block text-[13px] font-medium text-slate-700 mb-1">
                    About Me
                  </label>
                  <textarea
                    value={profileForm.bio}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, bio: e.target.value })
                    }
                    rows={3}
                    className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-colors"
                    placeholder="Tell us a bit about yourself, your interests, hobbies..."
                  />
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <Button
                  type="submit"
                  loading={isSaving}
                  className="w-full sm:w-auto bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  Save Changes
                </Button>
              </div>
            </form>
          </div>

          {/* Student Details — Read-only */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5 sm:p-6">
            <h2 className="text-[15px] font-semibold text-slate-900 mb-1">Student Details</h2>
            <p className="text-[13px] text-slate-500 mb-6">
              These details are managed by your school administration.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {studentDetails.map((detail) => (
                <div
                  key={detail.label}
                  className="flex items-start gap-3 rounded-xl bg-slate-50/80 border border-slate-100 p-4"
                >
                  <div className="flex-shrink-0 h-10 w-10 rounded-lg bg-indigo-50 flex items-center justify-center">
                    <detail.icon className="h-5 w-5 text-indigo-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">
                      {detail.label}
                    </p>
                    <p className="text-[14px] text-slate-800 font-medium mt-0.5 truncate">
                      {detail.value}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
