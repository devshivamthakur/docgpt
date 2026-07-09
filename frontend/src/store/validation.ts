import {
  PASSWORD_MIN_LENGTH,
  PASSWORD_PATTERN,
  EMAIL_PATTERN,
} from './constants';

export { PASSWORD_MIN_LENGTH, PASSWORD_PATTERN, EMAIL_PATTERN };

export interface ValidationResult {
  valid: boolean;
  message: string;
}

export function validateEmail(email: string): ValidationResult {
  if (!email.trim()) {
    return { valid: false, message: 'Email is required' };
  }
  if (!EMAIL_PATTERN.test(email)) {
    return { valid: false, message: 'Please enter a valid email address' };
  }
  return { valid: true, message: '' };
}

export function validatePassword(password: string): ValidationResult {
  if (!password) {
    return { valid: false, message: 'Password is required' };
  }
  if (password.length < PASSWORD_MIN_LENGTH) {
    return {
      valid: false,
      message: `Password must be at least ${PASSWORD_MIN_LENGTH} characters`,
    };
  }
  if (!PASSWORD_PATTERN.test(password)) {
    return {
      valid: false,
      message:
        'Password must include uppercase, lowercase, a number, and a special character (!@#$%^&*()-_=+{};:,<.>)',
    };
  }
  return { valid: true, message: '' };
}

export function validateName(name: string): ValidationResult {
  if (!name.trim()) {
    return { valid: false, message: 'Full name is required' };
  }
  return { valid: true, message: '' };
}
