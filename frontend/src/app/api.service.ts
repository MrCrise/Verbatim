import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export interface MeetingResponse {
  id: string;
  title: string;
  status: string;
  created_at: string;
  duration?: string;
  participantCount?: number;
  participants?: { name: string }[];
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
        if (res && res.access_token) {
          localStorage.setItem('token', res.access_token);
        }
      })
    );
  }

  register(data: any): Observable<any> {
    return this.http.post(`${this.baseUrl}/auth/register`, data);
  }

  getMeetings(): Observable<MeetingResponse[]> {
    return this.http.get<MeetingResponse[]>(`${this.baseUrl}/meetings/`, { headers: this.getHeaders() });
  }

  getMeeting(id: string): Observable<MeetingResponse> {
    return this.http.get<MeetingResponse>(`${this.baseUrl}/meetings/${id}`, { headers: this.getHeaders() });
  }

  // ДОБАВЛЕН ПАРАМЕТР TITLE
  uploadFile(file: File, title?: string): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    if (title) {
      formData.append('title', title);
    }
    return this.http.post(`${this.baseUrl}/transcribe/upload`, formData, { headers: this.getHeaders() });
  }

  downloadAudio(id: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/meetings/${id}/download`, { headers: this.getHeaders(), responseType: 'blob' });
  }

  streamAudio(id: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/meetings/${id}/stream`, { headers: this.getHeaders(), responseType: 'blob' });
  }
}
