import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { adminTeachersService } from '../../services/adminTeachersService';
import { MagnifyingGlassIcon, UserPlusIcon } from '@heroicons/react/24/outline';

export const TeachersPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: teachers, isLoading } = useQuery({
    queryKey: ['adminTeachers', search],
    queryFn: () => adminTeachersService.listTeachers({ search }),
  });

  const rows = useMemo(() => teachers ?? [], [teachers]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Teachers</h1>
          <p className="mt-1 text-sm text-gray-500">Create and manage teacher accounts.</p>
        </div>
        <Button
          variant="primary"
          className="bg-primary-600 hover:bg-primary-700"
          onClick={() => navigate('/admin/teachers/new')}
        >
          <UserPlusIcon className="h-4 w-4 mr-2" />
          Create Teacher
        </Button>
      </div>

      <div className="card">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email"
              leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            />
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-gray-500">
            <tr>
              <th className="py-3 pr-6">Name</th>
              <th className="py-3 pr-6">Email</th>
              <th className="py-3 pr-6">Role</th>
              <th className="py-3 pr-6">Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td className="py-6 text-gray-500" colSpan={4}>
                  Loading…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td className="py-6 text-gray-500" colSpan={4}>
                  No teachers found.
                </td>
              </tr>
            ) : (
              rows.map((t) => (
                <tr key={t.id} className="text-gray-800">
                  <td className="py-3 pr-6 font-medium">
                    {t.first_name} {t.last_name}
                  </td>
                  <td className="py-3 pr-6">{t.email}</td>
                  <td className="py-3 pr-6">{t.role}</td>
                  <td className="py-3 pr-6">{t.is_active ? 'Yes' : 'No'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

