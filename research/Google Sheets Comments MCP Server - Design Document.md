# Google Sheets Comments MCP Server - Design Document

## Executive Summary

This document outlines the design for a specialized Model Context Protocol (MCP) server that provides comprehensive comment management capabilities for Google Sheets. The server addresses a critical gap in the current MCP ecosystem by enabling AI agents to intelligently interact with comments in collaborative Google Sheets workflows.

### Key Value Proposition
- **First-of-its-kind**: No existing MCP server supports Google Sheets comments
- **Context-Aware**: Smart filtering prevents AI context overflow with thousands of comments  
- **Performance-Optimized**: Intelligent caching reduces API calls by 50x+
- **Workflow-Integrated**: Designed for collaborative document review processes

---

## 1. Project Scope

### 1.1 Primary Objectives

#### **Core Functionality**
- ✅ Full CRUD operations for Google Sheets comments and replies
- ✅ Spatial filtering (by cell, row, column, range)
- ✅ Resolution management (resolve/unresolve comments via action replies)
- ✅ Author attribution and metadata access
- ✅ Soft deletion handling

#### **Critical Performance Features**
- 🔥 **Intelligent caching system** with automatic invalidation
- 🔥 **Context management** to prevent AI overflow with large comment sets
- 🔥 **Spatial indexing** for instant filtering by location

#### **Integration Architecture**
- 🏗️ **Standalone design**: Works alongside separate Sheets/Docs MCP servers
- 🏗️ **Clean separation**: Comments-only functionality
- 🏗️ **Workflow support**: Integrates with external tracking spreadsheets

### 1.2 Target Use Cases

#### **Internal Collaboration Workflows**
- Analyst reviews volunteer work on assigned spreadsheet rows
- Comment-based feedback and quality assurance processes
- Progress tracking and assignment management

#### **Public Review Workflows**  
- Mass comment review during public comment periods
- Categorization and analysis of external feedback
- Bulk resolution of review comments

#### **General Comment Management**
- Spatial comment filtering for focused work sessions
- Resolution workflow management
- Comment export and analysis

### 1.3 Explicit Non-Goals

#### **Out of Scope**
- ❌ Reading/writing spreadsheet cell data (handled by separate Sheets MCP server)
- ❌ Document content management (handled by separate Docs MCP server)
- ❌ Native @mention notifications (Google Drive API limitation)
- ❌ Real-time collaborative features
- ❌ Advanced analytics/reporting (beyond basic comment analysis)

---

## 2. Architecture Design

### 2.1 MCP Server Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Host (Claude Desktop, etc.)          │
├─────────────────────────────────────────────────────────────┤
│  📊 Sheets MCP Client  │  💬 Comments MCP Client (this)     │
├─────────────────────────────────────────────────────────────┤
│                     JSON-RPC Transport                      │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│               Comments MCP Server Process                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  Cache Manager  │  │ Spatial Indexer │  │ API Gateway │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Google Drive API                         │
│           (Comments & Replies Resources)                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Core Components

#### **Protocol Layer**
- **Transport**: Stdio (for local execution) or SSE (for remote deployment)
- **Message Format**: JSON-RPC 2.0 as per MCP specification
- **Error Handling**: Standard MCP error codes plus custom comment-specific codes

#### **Cache Management System**
```typescript
interface CommentCache {
  spreadsheetId: string;
  lastFetched: Date;
  comments: Comment[];
  spatialIndex: {
    [key: string]: string[]; // cell/row/col -> commentIds
  };
  metadata: {
    totalComments: number;
    resolvedCount: number;
    openCount: number;
  };
}
```

#### **Spatial Indexing Engine**
```typescript
interface SpatialIndex {
  // Direct cell references
  'A1': string[];
  'B5': string[];
  
  // Row references  
  'row_1': string[];
  'row_5': string[];
  
  // Column references
  'col_A': string[];
  'col_B': string[];
  
  // Range references
  'A1:B5': string[];
}
```

### 2.3 Authentication & Authorization

#### **OAuth 2.0 Configuration**
- **Scopes Required**:
  - `https://www.googleapis.com/auth/drive` (full Drive access)
  - `https://www.googleapis.com/auth/drive.file` (file-specific access)
- **Credential Types Supported**:
  - Service Account (recommended for server deployments)
  - OAuth Client ID (for user-specific access)
  - Environment variable injection (for containerized deployments)

#### **Permission Model**
- **Read Operations**: Requires reader access to spreadsheet
- **Write Operations**: Requires commenter access to spreadsheet  
- **Delete Operations**: Must be comment author or file owner

---

## 3. MCP Tools Specification

### 3.1 Core Comment Operations

#### **get_comments_for_cell**
```typescript
{
  name: "get_comments_for_cell",
  description: "Get all comments anchored to a specific cell",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string", description: "Google Sheets ID" },
      cell: { type: "string", description: "Cell reference (e.g., 'A1')" },
      includeResolved: { type: "boolean", default: true },
      forceRefresh: { type: "boolean", default: false }
    },
    required: ["spreadsheetId", "cell"]
  }
}
```

#### **get_comments_for_row**
```typescript
{
  name: "get_comments_for_row",
  description: "Get all comments anchored to any cell in a specific row",
  inputSchema: {
    type: "object", 
    properties: {
      spreadsheetId: { type: "string" },
      row: { type: "number", description: "Row number (1-based)" },
      includeResolved: { type: "boolean", default: true },
      forceRefresh: { type: "boolean", default: false }
    },
    required: ["spreadsheetId", "row"]
  }
}
```

#### **get_comments_for_column**
```typescript
{
  name: "get_comments_for_column", 
  description: "Get all comments anchored to any cell in a specific column",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" },
      column: { type: "string", description: "Column letter (e.g., 'A')" },
      includeResolved: { type: "boolean", default: true },
      forceRefresh: { type: "boolean", default: false }
    },
    required: ["spreadsheetId", "column"]
  }
}
```

#### **create_comment**
```typescript
{
  name: "create_comment",
  description: "Create a new comment on a cell or range",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" },
      content: { type: "string", description: "Comment text content" },
      anchor: {
        type: "object",
        properties: {
          cell: { type: "string", description: "Single cell (e.g., 'A1')" },
          range: { type: "string", description: "Cell range (e.g., 'A1:B5')" },
          row: { type: "number", description: "Entire row" },
          column: { type: "string", description: "Entire column" }
        }
      }
    },
    required: ["spreadsheetId", "content", "anchor"]
  }
}
```

#### **reply_to_comment**
```typescript
{
  name: "reply_to_comment",
  description: "Add a reply to an existing comment",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" },
      commentId: { type: "string" },
      content: { type: "string", description: "Reply text content" },
      action: { 
        type: "string", 
        enum: ["resolve", "reopen"], 
        description: "Optional action to perform"
      }
    },
    required: ["spreadsheetId", "commentId", "content"]
  }
}
```

### 3.2 Resolution Management

#### **resolve_comment**
```typescript
{
  name: "resolve_comment",
  description: "Mark a comment as resolved",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" },
      commentId: { type: "string" },
      resolutionNote: { type: "string", description: "Optional resolution note" }
    },
    required: ["spreadsheetId", "commentId"]
  }
}
```

#### **reopen_comment**
```typescript
{
  name: "reopen_comment", 
  description: "Reopen a resolved comment",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" },
      commentId: { type: "string" },
      reopenNote: { type: "string", description: "Optional reason for reopening" }
    },
    required: ["spreadsheetId", "commentId"]
  }
}
```

### 3.3 Cache Management

#### **refresh_comments**
```typescript
{
  name: "refresh_comments",
  description: "Force refresh comment cache for a spreadsheet",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" }
    },
    required: ["spreadsheetId"]
  }
}
```

#### **get_cache_status**
```typescript
{
  name: "get_cache_status",
  description: "Get information about comment cache status",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" }
    },  
    required: ["spreadsheetId"]
  }
}
```

### 3.4 Bulk Operations

#### **list_all_comments**
```typescript
{
  name: "list_all_comments",
  description: "List all comments in a spreadsheet with optional filtering",
  inputSchema: {
    type: "object",
    properties: {
      spreadsheetId: { type: "string" },
      filters: {
        type: "object",
        properties: {
          resolved: { type: "boolean", description: "Filter by resolution status" },
          author: { type: "string", description: "Filter by author email" },
          dateRange: {
            type: "object",
            properties: {
              start: { type: "string", format: "date-time" },
              end: { type: "string", format: "date-time" }
            }
          }
        }
      },
      includeReplies: { type: "boolean", default: true },
      forceRefresh: { type: "boolean", default: false }
    },
    required: ["spreadsheetId"]
  }
}
```

#### **delete_comment**
```typescript
{
  name: "delete_comment",
  description: "Delete a comment (soft delete)",
  inputSchema: {
    type: "object", 
    properties: {
      spreadsheetId: { type: "string" },
      commentId: { type: "string" },
      reason: { type: "string", description: "Optional deletion reason" }
    },
    required: ["spreadsheetId", "commentId"]
  }
}
```

---

## 4. Caching Strategy

### 4.1 Cache Architecture

#### **Two-Mode Operation**
1. **Fresh Fetch Mode**: Initial request triggers full API fetch and cache population
2. **Cached Mode**: Subsequent requests served from memory cache

#### **Cache Structure**
```typescript
class CommentCacheManager {
  private caches = new Map<string, CommentCache>();
  private readonly MAX_CACHE_AGE = 60 * 60 * 1000; // 1 hour safety net
  
  async getComments(spreadsheetId: string, forceRefresh = false): Promise<Comment[]>
  async invalidateCache(spreadsheetId: string): Promise<void>
  async buildSpatialIndex(comments: Comment[]): Promise<SpatialIndex>
}
```

### 4.2 Cache Invalidation Strategy

#### **Automatic Invalidation Triggers**
- ✅ Comment creation → Invalidate cache
- ✅ Comment modification → Invalidate cache  
- ✅ Comment deletion → Invalidate cache
- ✅ Reply creation → Invalidate cache (changes parent modifiedTime)
- ✅ Comment resolution → Invalidate cache

#### **Manual Invalidation**
- ✅ User-requested refresh via `refresh_comments` tool
- ✅ Configurable max cache age (default: 1 hour)

### 4.3 Performance Benefits

#### **Speed Improvements**
- **First Request**: ~2-5 seconds (API + processing)
- **Cached Requests**: ~50-100ms (memory lookup + filtering)
- **Improvement Factor**: 50x+ for subsequent requests

#### **API Efficiency**
- **Without Cache**: Every spatial filter = new API call
- **With Cache**: One API call serves unlimited spatial filters
- **Rate Limit Compliance**: Stays well within Google Drive API limits

---

## 5. Implementation Plan

### 5.1 Development Phases

#### **Phase 1: Core Infrastructure (Weeks 1-2)**
- ✅ MCP server scaffolding with TypeScript SDK
- ✅ Google Drive API integration and authentication
- ✅ Basic comment CRUD operations
- ✅ Error handling and logging

#### **Phase 2: Caching System (Weeks 3-4)**
- ✅ In-memory cache implementation
- ✅ Automatic invalidation logic
- ✅ Cache management tools
- ✅ Performance optimization

#### **Phase 3: Spatial Intelligence (Weeks 5-6)**
- ✅ Anchor parsing and validation
- ✅ Spatial indexing system
- ✅ Cell/row/column filtering tools
- ✅ Context management features

#### **Phase 4: Advanced Features (Weeks 7-8)**
- ✅ Resolution workflow management
- ✅ Bulk operations and filtering
- ✅ @mention detection (basic text parsing)
- ✅ Export and analysis capabilities

#### **Phase 5: Testing & Documentation (Weeks 9-10)**
- ✅ Comprehensive unit testing
- ✅ Integration testing with real spreadsheets
- ✅ Performance benchmarking
- ✅ Documentation and examples

### 5.2 Technology Stack

#### **Core Technologies**
- **Language**: TypeScript (for type safety and MCP SDK compatibility)
- **MCP SDK**: `@modelcontextprotocol/sdk`
- **Google API**: `googleapis` npm package
- **Transport**: Stdio (primary) with SSE fallback option

#### **Development Tools**
- **Testing**: Jest for unit testing
- **Linting**: ESLint + Prettier
- **Build**: TypeScript compiler with npm scripts
- **CI/CD**: GitHub Actions for automated testing and releases

### 5.3 Deployment Options

#### **Local Development**
```bash
# Install and run locally
npm install -g google-sheets-comments-mcp
google-sheets-comments-mcp --credentials-path ./service-account.json
```

#### **Claude Desktop Integration**
```json
{
  "mcpServers": {
    "google-sheets-comments": {
      "command": "node",
      "args": ["/path/to/google-sheets-comments-mcp/dist/index.js"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json"
      }
    }
  }
}
```

#### **Docker Deployment**
```dockerfile
FROM node:18-alpine
COPY . .
RUN npm ci --only=production
CMD ["node", "dist/index.js"]
```

---

## 6. Security & Compliance

### 6.1 Authentication Security

#### **OAuth 2.0 Best Practices**
- ✅ Service Account recommended for production
- ✅ Minimum required scopes (drive.file preferred over drive)
- ✅ Credential rotation support
- ✅ Environment variable configuration

#### **Access Control**
- ✅ Validate user permissions before operations
- ✅ Respect Google Drive sharing settings
- ✅ Author-only edit/delete restrictions
- ✅ Input validation for all parameters

### 6.2 Data Protection

#### **Cache Security**
- ✅ In-memory only (no persistent storage of comments)
- ✅ Cache encryption for sensitive spreadsheets
- ✅ Automatic cache expiration
- ✅ Memory usage limits and cleanup

#### **API Safety**
- ✅ Rate limiting to prevent abuse
- ✅ Request size limits
- ✅ Timeout handling for long operations
- ✅ Comprehensive error logging

### 6.3 Privacy Considerations

#### **Data Handling**
- ✅ No permanent storage of comment content
- ✅ Minimal data retention in logs
- ✅ Respect user privacy settings
- ✅ GDPR compliance considerations

---

## 7. Testing Strategy

### 7.1 Unit Testing

#### **Core Component Tests**
- ✅ Cache management operations
- ✅ Spatial indexing algorithms  
- ✅ Google Drive API integration
- ✅ MCP tool parameter validation
- ✅ Error handling scenarios

#### **Test Coverage Goals**
- **Target**: 90%+ code coverage
- **Focus Areas**: Cache invalidation, spatial filtering, error conditions
- **Tools**: Jest with coverage reporting

### 7.2 Integration Testing

#### **Real Spreadsheet Testing**
- ✅ Test with production-scale comment volumes (1000+ comments)
- ✅ Multi-user collaboration scenarios
- ✅ Various anchor formats and edge cases
- ✅ Performance testing under load

#### **MCP Protocol Testing**
- ✅ Client-server communication validation
- ✅ Error propagation testing
- ✅ Tool schema compliance verification
- ✅ Transport layer reliability

### 7.3 Performance Testing

#### **Benchmarking Targets**
- **Cache Hit Response**: <100ms for spatial filtering
- **Fresh Fetch**: <5 seconds for 1000+ comments
- **Memory Usage**: <100MB for typical spreadsheets
- **Concurrent Users**: Support 10+ simultaneous connections

---

## 8. Documentation Plan

### 8.1 User Documentation

#### **Quick Start Guide**
- Installation instructions
- Authentication setup
- Basic usage examples
- Claude Desktop integration

#### **Tool Reference**
- Complete tool documentation
- Parameter descriptions
- Response formats
- Error codes

#### **Use Case Examples**
- Internal collaboration workflows
- Public review processes
- Spatial filtering scenarios
- Cache management best practices

### 8.2 Developer Documentation

#### **Architecture Overview**
- System design diagrams
- Component interactions
- Data flow documentation
- Extension points

#### **API Reference**
- Google Drive API integration details
- MCP protocol implementation
- Custom error codes
- Performance characteristics

#### **Deployment Guide**
- Production deployment options
- Security configuration
- Monitoring and logging
- Troubleshooting guide

---

## 9. Success Metrics

### 9.1 Functional Success Criteria

#### **Core Functionality**
- ✅ 100% Google Drive Comments API method coverage
- ✅ Sub-100ms response times for cached operations
- ✅ Support for spreadsheets with 10,000+ comments
- ✅ Zero data loss in cache invalidation scenarios

#### **User Experience**
- ✅ Intuitive tool naming and descriptions
- ✅ Clear error messages and handling
- ✅ Seamless integration with existing MCP workflows
- ✅ Comprehensive documentation and examples

### 9.2 Performance Metrics

#### **Speed Targets**
- **Cache Hit**: <100ms response time
- **API Fetch**: <5s for 1000 comments
- **Memory Usage**: <100MB typical, <500MB maximum
- **Startup Time**: <2s server initialization

#### **Reliability Targets**
- **Uptime**: 99.9% availability for long-running processes
- **Error Rate**: <1% for normal operations
- **Cache Consistency**: 100% accuracy after invalidation
- **API Compliance**: Zero rate limit violations

### 9.3 Adoption Metrics

#### **Community Success**
- GitHub stars and forks
- User-reported use cases and feedback
- Integration examples from community
- Documentation clarity ratings

#### **Ecosystem Impact**
- First production-ready comments MCP server
- Reference implementation for other Google API integrations
- Foundation for advanced comment analytics tools
- Catalyst for other collaborative workflow MCP servers

---

## 10. Future Roadmap

### 10.1 Planned Enhancements

#### **Version 1.1 - Advanced Analytics**
- Comment sentiment analysis
- Bulk comment summarization
- Trend analysis over time
- Export to external analytics tools

#### **Version 1.2 - Enhanced Collaboration**
- Real-time comment change notifications
- Advanced @mention parsing and notifications
- Integration with external notification systems
- Comment workflow automation

#### **Version 1.3 - Multi-Platform Support**
- Google Docs comment support
- Google Slides comment support
- Unified comment interface across Google Workspace
- Cross-document comment analysis

### 10.2 Potential Extensions

#### **Enterprise Features**
- Audit logging and compliance reporting
- Advanced access control and permissions
- Custom comment workflows and approval processes
- Integration with enterprise identity systems

#### **AI-Specific Features**
- Comment quality scoring
- Automated response suggestions
- Language translation for international collaboration
- Context-aware comment summarization

---

## Conclusion

The Google Sheets Comments MCP Server represents a critical missing piece in the MCP ecosystem, enabling AI agents to intelligently interact with collaborative comment workflows. By combining comprehensive Google Drive API coverage with smart caching and spatial filtering, this server transforms comment management from a manual, overwhelming task into an efficient, AI-assisted process.

The project's success will be measured not just by technical functionality, but by its impact on real-world collaborative workflows - enabling analysts to efficiently review volunteer contributions, process public feedback, and maintain high-quality collaborative documents at scale.

**Key Success Factors:**
- **Technical Excellence**: Robust, performant, and reliable implementation
- **User Experience**: Intuitive tools that solve real workflow problems  
- **Community Impact**: First-mover advantage in comment-enabled MCP servers
- **Ecosystem Integration**: Clean separation of concerns with other MCP servers

This design document provides the foundation for building a production-ready MCP server that will define the standard for comment management in AI-assisted collaborative workflows.

