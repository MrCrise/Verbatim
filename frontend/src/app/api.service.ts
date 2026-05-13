import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export interface MeetingResponse {
  id: string;
  title: string;
  status: string;
  created_at: string;
  duration_sec?: number;
  participant_count?: number;
  speakers_map?: Record<string, string>;
  transcript_data?: {
    segments: any[];
    full_text: string;
    speakers: string[];
  };
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private baseUrl = 'http://localhost:8000/api/v1';

  constructor(private http: HttpClient) {}

  private getHeaders() {
    const token = localStorage.getItem('token');
    return new HttpHeaders().set('Authorization', `Bearer ${token || ''}`);
  }

  login(formData: FormData): Observable<any> {
    return this.http.post(`${this.baseUrl}/auth/login`, formData).pipe(
      tap((res: any) => {
        if (res && res.access_token) localStorage.setItem('token', res.access_token);
      })
    );
  }

  register(data: any): Observable<any> {
    return this.http.post(`${this.baseUrl}/auth/register`, data);
  }

  getCurrentUser(): Observable<any> {
    return this.http.get(`${this.baseUrl}/debug/me`, { headers: this.getHeaders() });
  }

  getMeetings(): Observable<MeetingResponse[]> {
    return this.http.get<MeetingResponse[]>(`${this.baseUrl}/meetings/`, { headers: this.getHeaders() });
  }

  getMeeting(id: string): Observable<MeetingResponse> {
    return this.http.get<MeetingResponse>(`${this.baseUrl}/meetings/${id}`, { headers: this.getHeaders() });
  }

  uploadFile(file: File, title?: string): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    return this.http.post(`${this.baseUrl}/transcribe/upload`, formData, { headers: this.getHeaders() });
  }

  updateSpeaker(meetingId: string, speakerId: string, realName: string): Observable<any> {
    return this.http.patch(`${this.baseUrl}/meetings/${meetingId}/speakers`, { speaker_id: speakerId, real_name: realName }, { headers: this.getHeaders() });
  }

  getAdminStats(): Observable<any> {
    return this.http.get(`${this.baseUrl}/admin/stats`, { headers: this.getHeaders() });
  }

  getAdminUsers(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/admin/users`, { headers: this.getHeaders() });
  }

  updateUserRole(userId: string, isAdmin: boolean): Observable<any> {
    return this.http.patch(`${this.baseUrl}/admin/users/${userId}/role?is_admin=${isAdmin}`, {}, { headers: this.getHeaders() });
  }

  downloadAudio(id: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/meetings/${id}/download`, { headers: this.getHeaders(), responseType: 'blob' });
  }

  streamAudio(id: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/meetings/${id}/stream`, { headers: this.getHeaders(), responseType: 'blob' });
  }
}
