import { Component, ViewChild, AfterViewInit } from '@angular/core';
import { ChatComponent } from './chat/chat.component';
import { LucideAngularModule, MessageSquare, Zap, Settings, Moon, Brain, Database, FileText, Link, Lock } from 'lucide-angular';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [ChatComponent, LucideAngularModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements AfterViewInit {
  @ViewChild(ChatComponent) chatComponent!: ChatComponent;

  // Lucide icons
  readonly MessageSquare = MessageSquare;
  readonly Zap = Zap;
  readonly Settings = Settings;
  readonly Moon = Moon;
  readonly Brain = Brain;
  readonly Database = Database;
  readonly FileText = FileText;
  readonly Link = Link;
  readonly Lock = Lock;

  ngAfterViewInit() {
    setTimeout(() => {}, 0);
  }

  openChat() {
    if (this.chatComponent && !this.chatComponent.isChatOpen) {
      this.chatComponent.toggleChat();
    }
  }
}