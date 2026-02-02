// src/pages/teacher/ProfilePage.tsx

import React, { useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import {
  UserCircleIcon,
  EnvelopeIcon,
  BriefcaseIcon,
  AcademicCapIcon,
  KeyIcon,
  BellIcon,
} from '@heroicons/react/24/outline';

export const ProfilePage: React.FC = () => {
  const toast = useToast();
  const { user } = useAuthStore();
  const [activeSection, setActiveSection] = useState<'profile' | 'password' | 'notifications'>('profile');
  const [isSaving, setIsSaving] = useState(false);
  
  // Profile form state
  const [profileForm, setProfileForm] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    email: user?.email || '',
    department: user?.department || '',
    employee_id: user?.employee_id || '',
  });
  
  // Password form state
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });
  
  // Notification settings
  const [notifications, setNotifications] = useState({
    email_course_updates: true,
    email_assignment_reminders: true,
    email_deadline_alerts: true,
    browser_notifications: false,
  });
  
  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    // TODO: API call to update profile
    await new Promise(resolve => setTimeout(resolve, 1000));
    setIsSaving(false);
    toast.success('Profile updated', 'Your profile has been saved.');
  };
  
  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      toast.error('Passwords do not match', 'Please ensure both passwords are the same.');
      return;
    }
    setIsSaving(true);
    // TODO: API call to change password
    await new Promise(resolve => setTimeout(resolve, 1000));
    setIsSaving(false);
    setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
    toast.success('Password updated', 'Your password has been changed.');
  };
  
  const handleNotificationsSave = async () => {
    setIsSaving(true);
    // TODO: API call to update notification settings
    await new Promise(resolve => setTimeout(resolve, 1000));
    setIsSaving(false);
    toast.success('Preferences saved', 'Your notification preferences have been updated.');
  };
  
  const sections = [
    { id: 'profile', label: 'Profile', icon: UserCircleIcon },
    { id: 'password', label: 'Password', icon: KeyIcon },
    { id: 'notifications', label: 'Notifications', icon: BellIcon },
  ];
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Profile Settings</h1>
        <p className="mt-1 text-gray-500">
          Manage your account settings and preferences
        </p>
      </div>
      
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar */}
        <div className="lg:w-64 flex-shrink-0">
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            {/* User avatar */}
            <div className="p-6 text-center border-b border-gray-100">
              <div className="h-20 w-20 mx-auto rounded-full bg-emerald-100 flex items-center justify-center mb-3">
                <span className="text-2xl font-semibold text-emerald-700">
                  {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
                </span>
              </div>
              <h3 className="font-semibold text-gray-900">
                {user?.first_name} {user?.last_name}
              </h3>
              <p className="text-sm text-gray-500">{user?.role?.replace('_', ' ')}</p>
            </div>
            
            {/* Navigation */}
            <nav className="p-2">
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id as typeof activeSection)}
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
        
        {/* Content */}
        <div className="flex-1">
          <div className="bg-white rounded-xl border border-gray-100 p-6">
            {/* Profile Section */}
            {activeSection === 'profile' && (
              <form onSubmit={handleProfileSubmit}>
                <h2 className="text-lg font-semibold text-gray-900 mb-6">Profile Information</h2>
                
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
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
                    onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                    leftIcon={<EnvelopeIcon className="h-5 w-5" />}
                    disabled
                    helperText="Contact admin to change email"
                  />
                  
                  <Input
                    label="Employee ID"
                    value={profileForm.employee_id}
                    onChange={(e) => setProfileForm({ ...profileForm, employee_id: e.target.value })}
                    leftIcon={<BriefcaseIcon className="h-5 w-5" />}
                    disabled
                  />
                  
                  <div className="sm:col-span-2">
                    <Input
                      label="Department"
                      value={profileForm.department}
                      onChange={(e) => setProfileForm({ ...profileForm, department: e.target.value })}
                      leftIcon={<AcademicCapIcon className="h-5 w-5" />}
                    />
                  </div>
                </div>
                
                <div className="mt-6 flex justify-end">
                  <Button type="submit" loading={isSaving} className="bg-emerald-600 hover:bg-emerald-700">
                    Save Changes
                  </Button>
                </div>
              </form>
            )}
            
            {/* Password Section */}
            {activeSection === 'password' && (
              <form onSubmit={handlePasswordSubmit}>
                <h2 className="text-lg font-semibold text-gray-900 mb-6">Change Password</h2>
                
                <div className="max-w-md space-y-6">
                  <Input
                    label="Current Password"
                    type="password"
                    value={passwordForm.current_password}
                    onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
                    leftIcon={<KeyIcon className="h-5 w-5" />}
                    required
                  />
                  
                  <Input
                    label="New Password"
                    type="password"
                    value={passwordForm.new_password}
                    onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                    leftIcon={<KeyIcon className="h-5 w-5" />}
                    helperText="Must be at least 8 characters"
                    required
                  />
                  
                  <Input
                    label="Confirm New Password"
                    type="password"
                    value={passwordForm.confirm_password}
                    onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                    leftIcon={<KeyIcon className="h-5 w-5" />}
                    required
                  />
                </div>
                
                <div className="mt-6 flex justify-end">
                  <Button type="submit" loading={isSaving} className="bg-emerald-600 hover:bg-emerald-700">
                    Update Password
                  </Button>
                </div>
              </form>
            )}
            
            {/* Notifications Section */}
            {activeSection === 'notifications' && (
              <div>
                <h2 className="text-lg font-semibold text-gray-900 mb-6">Notification Preferences</h2>
                
                <div className="space-y-4">
                  <div className="flex items-center justify-between py-3 border-b border-gray-100">
                    <div>
                      <p className="font-medium text-gray-900">Course Updates</p>
                      <p className="text-sm text-gray-500">Get notified when courses are updated</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={notifications.email_course_updates}
                        onChange={(e) => setNotifications({ ...notifications, email_course_updates: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                    </label>
                  </div>
                  
                  <div className="flex items-center justify-between py-3 border-b border-gray-100">
                    <div>
                      <p className="font-medium text-gray-900">Assignment Reminders</p>
                      <p className="text-sm text-gray-500">Receive reminders for pending assignments</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={notifications.email_assignment_reminders}
                        onChange={(e) => setNotifications({ ...notifications, email_assignment_reminders: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                    </label>
                  </div>
                  
                  <div className="flex items-center justify-between py-3 border-b border-gray-100">
                    <div>
                      <p className="font-medium text-gray-900">Deadline Alerts</p>
                      <p className="text-sm text-gray-500">Get alerts before deadlines approach</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={notifications.email_deadline_alerts}
                        onChange={(e) => setNotifications({ ...notifications, email_deadline_alerts: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                    </label>
                  </div>
                  
                  <div className="flex items-center justify-between py-3">
                    <div>
                      <p className="font-medium text-gray-900">Browser Notifications</p>
                      <p className="text-sm text-gray-500">Enable desktop push notifications</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={notifications.browser_notifications}
                        onChange={(e) => setNotifications({ ...notifications, browser_notifications: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                    </label>
                  </div>
                </div>
                
                <div className="mt-6 flex justify-end">
                  <Button onClick={handleNotificationsSave} loading={isSaving} className="bg-emerald-600 hover:bg-emerald-700">
                    Save Preferences
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
