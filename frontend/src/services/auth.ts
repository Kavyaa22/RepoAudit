import { apiClient } from "./api-client";

type ApiEnvelope<T> = { success: boolean; data: T };

export type MeProfile = {
  user_id: string | null;
  email: string | null;
  full_name: string | null;
  message?: string;
};

export async function fetchMe(): Promise<MeProfile> {
  const { data } = await apiClient.get<ApiEnvelope<MeProfile>>("/auth/me");
  return data.data;
}

export async function updateMe(fullName: string): Promise<MeProfile> {
  const { data } = await apiClient.patch<ApiEnvelope<MeProfile>>("/auth/me", {
    full_name: fullName,
  });
  return data.data;
}

export async function deleteMe(password: string): Promise<MeProfile> {
  const { data } = await apiClient.delete<ApiEnvelope<MeProfile>>("/auth/me", {
    data: { password },
  });
  return data.data;
}
