// pages/settings/SecuritySettings.tsx
/**
 * Security settings page for SSO and 2FA configuration.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Loading } from '../../components/common';
import api from '../../config/api';

interface TwoFAStatus {
  enabled: boolean;
  required: boolean;
  totp_configured: boolean;
  backup_codes_remaining: number;
  can_disable: boolean;
}

interface SSOStatus {
  has_password: boolean;
  linked_providers: Array<{
    provider: string;
    uid: string;
  }>;
  can_unlink: boolean;
}

interface SSOProviders {
  providers: Array<{
    id: string;
    name: string;
    icon: string;
    auth_url: string;
  }>;
  sso_enabled: boolean;
  sso_required: boolean;
}

export const SecuritySettings: React.FC = () => {
  const queryClient = useQueryClient();
  const [setupStep, setSetupStep] = useState<'idle' | 'scanning' | 'verifying'>('idle');
  const [qrData, setQrData] = useState<{ qr_code: string; secret: string } | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [showBackupCodes, setShowBackupCodes] = useState(false);

  // Fetch 2FA status
  const { data: twoFAStatus, isLoading: loadingTwoFA } = useQuery<TwoFAStatus>({
    queryKey: ['2fa-status'],
    queryFn: async () => {
      const response = await api.get('/users/auth/2fa/status/');
      return response.data;
    },
  });

  // Fetch SSO status
  const { data: ssoStatus, isLoading: loadingSSO } = useQuery<SSOStatus>({
    queryKey: ['sso-status'],
    queryFn: async () => {
      const response = await api.get('/users/auth/sso/status/');
      return response.data;
    },
  });

  // Fetch SSO providers
  const { data: ssoProviders } = useQuery<SSOProviders>({
    queryKey: ['sso-providers'],
    queryFn: async () => {
      const response = await api.get('/users/auth/sso/providers/');
      return response.data;
    },
  });

  // Start 2FA setup
  const startSetupMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/users/auth/2fa/setup/');
      return response.data;
    },
    onSuccess: (data) => {
      setQrData(data);
      setSetupStep('scanning');
    },
  });

  // Confirm 2FA setup
  const confirmSetupMutation = useMutation({
    mutationFn: async (code: string) => {
      const response = await api.post('/users/auth/2fa/confirm/', { code });
      return response.data;
    },
    onSuccess: (data) => {
      setBackupCodes(data.backup_codes);
      setShowBackupCodes(true);
      setSetupStep('idle');
      setQrData(null);
      setVerifyCode('');
      queryClient.invalidateQueries({ queryKey: ['2fa-status'] });
    },
  });

  // Disable 2FA
  const disableTwoFAMutation = useMutation({
    mutationFn: async ({ code, password }: { code: string; password: string }) => {
      const response = await api.post('/users/auth/2fa/disable/', { code, password });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['2fa-status'] });
    },
  });

  if (loadingTwoFA || loadingSSO) {
    return <Loading />;
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Security Settings</h1>

      {/* Two-Factor Authentication */}
      <section className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Two-Factor Authentication (2FA)
        </h2>

        {twoFAStatus?.enabled ? (
          <div>
            <div className="flex items-center gap-2 text-green-600 mb-4">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="font-medium">2FA is enabled</span>
            </div>

            <p className="text-sm text-gray-600 mb-4">
              Backup codes remaining: {twoFAStatus.backup_codes_remaining}
            </p>

            {twoFAStatus.can_disable && (
              <Button
                variant="outline"
                onClick={() => {
                  const code = prompt('Enter your 2FA code:');
                  const password = prompt('Enter your password:');
                  if (code && password) {
                    disableTwoFAMutation.mutate({ code, password });
                  }
                }}
              >
                Disable 2FA
              </Button>
            )}

            {twoFAStatus.required && (
              <p className="text-sm text-yellow-600 mt-2">
                Your organization requires 2FA. It cannot be disabled.
              </p>
            )}
          </div>
        ) : (
          <div>
            <p className="text-gray-600 mb-4">
              Add an extra layer of security to your account by enabling two-factor
              authentication.
            </p>

            {setupStep === 'idle' && (
              <Button onClick={() => startSetupMutation.mutate()}>
                Enable 2FA
              </Button>
            )}

            {setupStep === 'scanning' && qrData && (
              <div className="space-y-4">
                <p className="text-sm text-gray-600">
                  Scan this QR code with your authenticator app (Google Authenticator,
                  Authy, etc.)
                </p>

                {qrData.qr_code && (
                  <img
                    src={qrData.qr_code}
                    alt="2FA QR Code"
                    className="w-48 h-48 border rounded"
                  />
                )}

                <p className="text-sm text-gray-500">
                  Or enter this code manually: <code className="font-mono">{qrData.secret}</code>
                </p>

                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Enter 6-digit code"
                    value={verifyCode}
                    onChange={(e) => setVerifyCode(e.target.value)}
                    maxLength={6}
                    className="px-3 py-2 border rounded-md w-32"
                  />
                  <Button
                    onClick={() => confirmSetupMutation.mutate(verifyCode)}
                    disabled={verifyCode.length !== 6}
                  >
                    Verify
                  </Button>
                  <Button variant="outline" onClick={() => setSetupStep('idle')}>
                    Cancel
                  </Button>
                </div>

                {confirmSetupMutation.error && (
                  <p className="text-sm text-red-600">
                    {(confirmSetupMutation.error as Error).message}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Backup codes modal */}
        {showBackupCodes && backupCodes.length > 0 && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-md">
              <h3 className="text-lg font-semibold mb-4">Save Your Backup Codes</h3>
              <p className="text-sm text-gray-600 mb-4">
                These codes can be used to access your account if you lose your
                authenticator device. Each code can only be used once.
              </p>
              <div className="grid grid-cols-2 gap-2 mb-4">
                {backupCodes.map((code, i) => (
                  <code key={i} className="font-mono text-sm bg-gray-100 p-2 rounded">
                    {code}
                  </code>
                ))}
              </div>
              <p className="text-sm text-red-600 mb-4">
                Store these codes in a safe place. They will not be shown again.
              </p>
              <Button onClick={() => setShowBackupCodes(false)}>I&apos;ve saved my codes</Button>
            </div>
          </div>
        )}
      </section>

      {/* Single Sign-On */}
      <section className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Single Sign-On (SSO)</h2>

        {ssoProviders?.providers && ssoProviders.providers.length > 0 ? (
          <div className="space-y-4">
            <p className="text-gray-600">
              Link your account with external identity providers for easier sign-in.
            </p>

            {ssoProviders.providers.map((provider) => {
              const isLinked = ssoStatus?.linked_providers.some(
                (lp) => lp.provider === provider.id
              );

              return (
                <div
                  key={provider.id}
                  className="flex items-center justify-between p-4 border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
                      {provider.icon === 'google' && (
                        <svg className="w-6 h-6" viewBox="0 0 24 24">
                          <path
                            fill="#4285F4"
                            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                          />
                          <path
                            fill="#34A853"
                            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                          />
                          <path
                            fill="#FBBC05"
                            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                          />
                          <path
                            fill="#EA4335"
                            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                          />
                        </svg>
                      )}
                    </div>
                    <div>
                      <p className="font-medium">{provider.name}</p>
                      {isLinked && (
                        <p className="text-sm text-green-600">Connected</p>
                      )}
                    </div>
                  </div>

                  {isLinked ? (
                    ssoStatus?.can_unlink && (
                      <Button variant="outline" size="sm">
                        Unlink
                      </Button>
                    )
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => {
                        window.location.href = provider.auth_url;
                      }}
                    >
                      Connect
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-gray-500">
            Single Sign-On is not enabled for your organization.
          </p>
        )}
      </section>
    </div>
  );
};

export default SecuritySettings;
