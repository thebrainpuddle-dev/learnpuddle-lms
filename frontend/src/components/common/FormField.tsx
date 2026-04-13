// src/components/common/FormField.tsx
//
// A React Hook Form-aware wrapper around the existing <Input> component.
// Connects a field registered via `useZodForm` / `react-hook-form` to the
// <Input> component with automatic error display.
//
// Usage:
//   <FormField control={form.control} name="email" label="Email" type="email" />

import React from 'react';
import {
  Controller,
  type Control,
  type FieldPath,
  type FieldValues,
} from 'react-hook-form';
import { Input } from './Input';

interface FormFieldProps<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'name'> {
  /** React Hook Form control object from `useZodForm` / `useForm`. */
  control: Control<TFieldValues>;
  /** The name of the field (must match the Zod schema key). */
  name: TName;
  /** Human-readable label rendered above the input. */
  label?: string;
  /** Hint text shown below the input when there is no error. */
  helperText?: string;
  /** Icon rendered on the left side of the input. */
  leftIcon?: React.ReactNode;
  /** Icon rendered on the right side of the input. */
  rightIcon?: React.ReactNode;
}

/**
 * Controlled form field that bridges React Hook Form with the app's
 * `<Input>` component. Automatically surfaces validation errors.
 *
 * @example
 * <FormField
 *   control={form.control}
 *   name="email"
 *   label="Email address"
 *   type="email"
 *   leftIcon={<EnvelopeIcon className="h-5 w-5 text-gray-400" />}
 *   placeholder="you@school.com"
 * />
 */
export function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({
  control,
  name,
  label,
  helperText,
  leftIcon,
  rightIcon,
  ...inputProps
}: FormFieldProps<TFieldValues, TName>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Input
          {...inputProps}
          {...field}
          // Override value with empty string when undefined to keep input controlled
          value={field.value ?? ''}
          label={label}
          helperText={helperText}
          leftIcon={leftIcon}
          rightIcon={rightIcon}
          error={fieldState.error?.message}
          // Forward id so label htmlFor resolves correctly
          id={inputProps.id ?? name}
        />
      )}
    />
  );
}
