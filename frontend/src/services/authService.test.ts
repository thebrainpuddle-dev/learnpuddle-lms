// src/services/authService.test.ts

import { authService } from './authService';
import api from '../config/api';

// Mock the api module
jest.mock('../config/api');
const mockedApi = api as jest.Mocked<typeof api>;

describe('authService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('login', () => {
    it('should call login endpoint with credentials', async () => {
      const mockResponse = {
        data: {
          user: {
            id: 'user-123',
            email: 'test@example.com',
            first_name: 'John',
            last_name: 'Doe',
            role: 'TEACHER',
            is_active: true,
          },
          tokens: {
            access: 'mock-access-token',
            refresh: 'mock-refresh-token',
          },
        },
      };
      
      mockedApi.post.mockResolvedValueOnce(mockResponse);
      
      const credentials = { email: 'test@example.com', password: 'password123' };
      const result = await authService.login(credentials);
      
      expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/login/', credentials);
      expect(result).toEqual(mockResponse.data);
    });

    it('should throw error on invalid credentials', async () => {
      const error = new Error('Invalid credentials');
      mockedApi.post.mockRejectedValueOnce(error);
      
      const credentials = { email: 'test@example.com', password: 'wrong' };
      
      await expect(authService.login(credentials)).rejects.toThrow('Invalid credentials');
    });
  });

  describe('logout', () => {
    it('should call logout endpoint with refresh token', async () => {
      mockedApi.post.mockResolvedValueOnce({ data: {} });
      
      await authService.logout('mock-refresh-token');
      
      expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/logout/', {
        refresh_token: 'mock-refresh-token',
      });
    });
  });

  describe('getMe', () => {
    it('should fetch current user profile', async () => {
      const mockUser = {
        id: 'user-123',
        email: 'test@example.com',
        first_name: 'John',
        last_name: 'Doe',
        role: 'TEACHER',
        is_active: true,
      };
      
      mockedApi.get.mockResolvedValueOnce({ data: mockUser });
      
      const result = await authService.getMe();
      
      expect(mockedApi.get).toHaveBeenCalledWith('/users/auth/me/');
      expect(result).toEqual(mockUser);
    });
  });

  describe('refreshToken', () => {
    it('should refresh access token', async () => {
      const mockResponse = { data: { access: 'new-access-token' } };
      mockedApi.post.mockResolvedValueOnce(mockResponse);
      
      const result = await authService.refreshToken('mock-refresh-token');
      
      expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/refresh/', {
        refresh_token: 'mock-refresh-token',
      });
      expect(result).toEqual({ access: 'new-access-token' });
    });
  });

  describe('changePassword', () => {
    it('should call change password endpoint', async () => {
      mockedApi.post.mockResolvedValueOnce({ data: {} });
      
      await authService.changePassword('oldPass123', 'newPass456');
      
      expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/change-password/', {
        old_password: 'oldPass123',
        new_password: 'newPass456',
        new_password_confirm: 'newPass456',
      });
    });
  });

  describe('requestPasswordReset', () => {
    it('should request password reset email', async () => {
      mockedApi.post.mockResolvedValueOnce({ data: {} });
      
      await authService.requestPasswordReset('test@example.com');
      
      expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/request-password-reset/', {
        email: 'test@example.com',
      });
    });
  });

  describe('confirmPasswordReset', () => {
    it('should confirm password reset with uid and token', async () => {
      mockedApi.post.mockResolvedValueOnce({ data: {} });
      
      await authService.confirmPasswordReset('user-uid', 'reset-token', 'newPassword123');
      
      expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/confirm-password-reset/', {
        uid: 'user-uid',
        token: 'reset-token',
        new_password: 'newPassword123',
      });
    });
  });
});
