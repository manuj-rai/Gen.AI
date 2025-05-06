// src/app/services/chat.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

interface ChatResponse {
  response: string;
  tokens: number;
}

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  private apiUrl = 'http://localhost:5000/ask';

  constructor(private http: HttpClient) {}

  sendPrompt(prompt: string, model = 'gpt-4o'): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(this.apiUrl, { prompt, model });
  }
}
