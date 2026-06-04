import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export interface LocationEdit {
  id: number;
  location_id: number;
  field_name: string;
  original_value: any;
  new_value: any;
  status: 'Draft' | 'Pending' | 'Approved' | 'Publishing' | 'Published' | 'Failed';
  warning_acknowledged: boolean;
  version: number;
  actor_user_id: number;
  actor_role: string;
  created_at: string;
  updated_at: string;
  submitted_by_user_id?: number;
  rejection_note?: string;
  failure_reason?: string;
}

export interface ActivityLog {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  details: any;
  created_at: string;
}

export function useLocationWorkspace(locationId: string | number) {
  const queryClient = useQueryClient();
  const id = Number(locationId);

  // 1. Fetch Location Data
  const { data: location, isLoading: isLocationLoading } = useQuery<any>({
    queryKey: ['location', id],
    queryFn: () => api.get(`/locations/${id}`),
    enabled: !!id,
  });

  // 2. Fetch Listing Edits
  const { data: edits, isLoading: isEditsLoading, isError: isEditsError, refetch: refetchEdits } = useQuery<LocationEdit[]>({
    queryKey: ['location-edits', id],
    queryFn: () => api.get(`/locations/${id}/edits`),
    enabled: !!id,
    refetchInterval: (query) => {
      // Conditionally poll if any edit is in 'Publishing' status
      const hasPublishing = query.state.data?.some(edit => edit.status === 'Publishing');
      return hasPublishing ? 3000 : false;
    }
  });

  // 3. Fetch Activity Log
  const { data: activityLog, isLoading: isActivityLoading } = useQuery<ActivityLog[]>({
    queryKey: ['activity-log', id],
    queryFn: () => api.get(`/locations/${id}/activity`),
    enabled: !!id,
  });

  // 4. Mutations
  const approveMutation = useMutation({
    mutationFn: ({ editId, version }: { editId: number, version: number }) => 
      api.post(`/edits/${editId}/approve`, { version }),
    onMutate: async ({ editId }) => {
      await queryClient.cancelQueries({ queryKey: ['location-edits', id] });
      const previousEdits = queryClient.getQueryData<LocationEdit[]>(['location-edits', id]);
      
      queryClient.setQueryData<LocationEdit[]>(['location-edits', id], old => {
        if (!old) return old;
        return old.map(edit => edit.id === editId ? { ...edit, status: 'Approved' } : edit);
      });
      return { previousEdits };
    },
    onError: (err, variables, context) => {
      if (context?.previousEdits) {
        queryClient.setQueryData(['location-edits', id], context.previousEdits);
      }
      toast.error(err.message || 'Failed to approve edit');
    },
    onSuccess: () => {
      toast.success('Edit approved');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['location-edits', id] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ editId, version, rejection_note }: { editId: number, version: number, rejection_note: string }) => 
      api.post(`/edits/${editId}/reject`, { version, rejection_note }),
    onMutate: async ({ editId }) => {
      await queryClient.cancelQueries({ queryKey: ['location-edits', id] });
      const previousEdits = queryClient.getQueryData<LocationEdit[]>(['location-edits', id]);
      
      queryClient.setQueryData<LocationEdit[]>(['location-edits', id], old => {
        if (!old) return old;
        return old.map(edit => edit.id === editId ? { ...edit, status: 'Failed' } : edit);
      });
      return { previousEdits };
    },
    onError: (err, variables, context) => {
      if (context?.previousEdits) {
        queryClient.setQueryData(['location-edits', id], context.previousEdits);
      }
      toast.error(err.message || 'Failed to reject edit');
    },
    onSuccess: () => {
      toast.success('Edit rejected');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['location-edits', id] });
    }
  });

  const publishMutation = useMutation({
    mutationFn: ({ editId }: { editId: number }) => 
      api.post(`/edits/${editId}/publish`),
    onMutate: async ({ editId }) => {
      await queryClient.cancelQueries({ queryKey: ['location-edits', id] });
      const previousEdits = queryClient.getQueryData<LocationEdit[]>(['location-edits', id]);
      
      queryClient.setQueryData<LocationEdit[]>(['location-edits', id], old => {
        if (!old) return old;
        return old.map(edit => edit.id === editId ? { ...edit, status: 'Publishing' } : edit);
      });
      return { previousEdits };
    },
    onError: (err, variables, context) => {
      if (context?.previousEdits) {
        queryClient.setQueryData(['location-edits', id], context.previousEdits);
      }
      toast.error(err.message || 'Failed to publish edit');
    },
    onSuccess: () => {
      toast.success('Publishing started');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['location-edits', id] });
    },
  });

  const createEditMutation = useMutation({
    mutationFn: (payload: { field_name: string; new_value: any; warning_acknowledged: boolean }) =>
      api.post(`/locations/${id}/edits`, payload),
    onSuccess: () => {
      toast.success('Edit saved successfully');
      queryClient.invalidateQueries({ queryKey: ['location-edits', id] });
    },
    onError: (err) => {
      toast.error(err.message || 'Failed to save edit');
    }
  });

  const submitMutation = useMutation({
    mutationFn: ({ editId, version }: { editId: number, version: number }) => 
      api.post(`/edits/${editId}/submit`, { version }),
    onSuccess: () => {
      toast.success('Draft submitted for approval');
      queryClient.invalidateQueries({ queryKey: ['location-edits', id] });
    },
    onError: (err) => {
      toast.error(err.message || 'Failed to submit draft');
    }
  });

  return {
    location,
    isLocationLoading,
    edits,
    isEditsLoading,
    isEditsError,
    refetchEdits,
    activityLog,
    isActivityLoading,
    approveMutation,
    rejectMutation,
    publishMutation,
    createEditMutation,
    submitMutation,
  };
}
