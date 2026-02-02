// src/services/authService.ts

import api from '../config/api';
import { User, LoginCredentials, AuthTokens } from '../types';

export const authService = {
  /**
   * Login user
   */
  async login(credentials: LoginCredentials): Promise<{ user: User; tokens: AuthTokens }> {
    const response = await api.post('/users/auth/login/', credentials);
    return response.data;
  },
  
  /**
   * Logout user
   */
  async logout(refreshToken: string): Promise<void> {
    await api.post('/users/auth/logout/', { refresh_token: refreshToken });
  },
  
  /**
   * Get current user profile
   */
  async getMe(): Promise<User> {
    const response = await api.get('/users/auth/me/');
    return response.data;
  },
  
  /**
   * Refresh access token
   */
  async refreshToken(refreshToken: string): Promise<{ access: string }> {
    const response = await api.post('/users/auth/refresh/', {
      refresh_token: refreshToken,
    });
    return response.data;
  },
  
  /**
   * Change password
   */
  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await api.post('/users/auth/change-password/', {
      old_password: oldPassword,
      new_password: newPassword,
      new_password_confirm: newPassword,
    });
  },
};
