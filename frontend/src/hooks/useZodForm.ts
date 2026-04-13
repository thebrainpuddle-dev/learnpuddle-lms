// src/hooks/useZodForm.ts
//
// Type-safe wrapper around React Hook Form that wires up Zod schema validation.
// Usage:
//   const form = useZodForm({ schema: MySchema, defaultValues: { ... } });
//   <form onSubmit={form.handleSubmit(onValid)}>
//     <Controller control={form.control} name="email" ... />

import { zodResolver } from '@hookform/resolvers/zod';
import {
  useForm,
  type UseFormProps,
  type UseFormReturn,
  type DefaultValues,
  type FieldValues,
} from 'react-hook-form';
import { type ZodType, type ZodTypeDef } from 'zod';

type UseZodFormOptions<
  TSchema extends FieldValues,
  TDef extends ZodTypeDef = ZodTypeDef,
  TInput = TSchema,
> = Omit<UseFormProps<TSchema>, 'resolver'> & {
  schema: ZodType<TSchema, TDef, TInput>;
  defaultValues?: DefaultValues<TSchema>;
};

/**
 * Thin wrapper around `useForm` that automatically wires up Zod schema
 * validation via `@hookform/resolvers/zod`.
 *
 * @example
 * const LoginSchema = z.object({ email: z.string().email(), password: z.string().min(8) });
 * type LoginData = z.infer<typeof LoginSchema>;
 *
 * const form = useZodForm({ schema: LoginSchema, defaultValues: { email: '', password: '' } });
 */
export function useZodForm<
  TSchema extends FieldValues,
  TDef extends ZodTypeDef = ZodTypeDef,
  TInput = TSchema,
>({
  schema,
  defaultValues,
  ...rest
}: UseZodFormOptions<TSchema, TDef, TInput>): UseFormReturn<TSchema> {
  return useForm<TSchema>({
    resolver: zodResolver(schema),
    defaultValues,
    mode: 'onTouched', // validate on blur then live on change
    ...rest,
  });
}
