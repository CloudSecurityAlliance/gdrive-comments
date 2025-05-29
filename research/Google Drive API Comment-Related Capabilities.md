# Google Drive API Comment-Related Capabilities

## Overview

This document provides a comprehensive list of every comment-related API capability available in the Google Drive API. The API provides two main resource types for managing conversations: **Comments** and **Replies**, with full CRUD operations and advanced features like anchoring, resolution, and threading.

---

## Comments Resource

### Core Comment Operations

#### 1. **comments.create**
- **Method**: `POST`
- **Endpoint**: `/drive/v3/files/{fileId}/comments`
- **Purpose**: Creates a new comment on a file
- **Features**:
  - Support for anchored and unanchored comments
  - JSON anchor string for positioning (revision ID + region)
  - Content can be plain text or HTML
  - Automatic author attribution
- **Anchoring Support**:
  - **Anchored Comments**: Associated with specific location/region
  - **Unanchored Comments**: Associated with entire document
  - **Limitation**: Blob files only support unanchored comments

#### 2. **comments.get**
- **Method**: `GET`
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}`
- **Purpose**: Retrieves a specific comment by ID
- **Features**:
  - Returns full comment metadata and content
  - Includes all replies in chronological order
  - Optional inclusion of deleted comments via `includeDeleted` parameter
  - Field selection via `fields` parameter

#### 3. **comments.list**
- **Method**: `GET`
- **Endpoint**: `/drive/v3/files/{fileId}/comments`
- **Purpose**: Lists all comments on a file
- **Features**:
  - Pagination support with `pageToken`
  - Filter by modification time with `startModifiedTime`
  - Include deleted comments option
  - Returns comment metadata and reply counts

#### 4. **comments.update**
- **Method**: `PATCH` (v3) / `PUT` (v2)
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}`
- **Purpose**: Updates an existing comment with patch semantics
- **Features**:
  - Partial updates (only changed fields)
  - Cannot directly modify `resolved` status
  - Author restrictions (only creator can update)
  - Content and formatting updates

#### 5. **comments.patch** (v2 only)
- **Method**: `PATCH`
- **Endpoint**: `/drive/v2/files/{fileId}/comments/{commentId}`
- **Purpose**: Updates comment with patch semantics (bandwidth optimization)
- **Features**:
  - More efficient than full update
  - Supports partial field updates
  - Legacy v2 API method

#### 6. **comments.delete**
- **Method**: `DELETE`
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}`
- **Purpose**: Marks a comment as deleted
- **Features**:
  - Soft delete (comment marked as `deleted: true`)
  - Content fields removed from deleted comments
  - Author restrictions (only creator can delete)
  - Preserves comment structure for threading

---

## Replies Resource

### Core Reply Operations

#### 7. **replies.create**
- **Method**: `POST`
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}/replies`
- **Purpose**: Creates a reply to an existing comment
- **Features**:
  - Standard text replies
  - **Action-based replies** for comment resolution
  - Automatic threading and chronological ordering
  - Author attribution and timestamps

#### 8. **replies.get**
- **Method**: `GET`
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}`
- **Purpose**: Retrieves a specific reply by ID
- **Features**:
  - Full reply metadata and content
  - Action information (resolve/reopen)
  - Author and timestamp details
  - Deletion status

#### 9. **replies.list**
- **Method**: `GET`
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}/replies`
- **Purpose**: Lists all replies to a specific comment
- **Features**:
  - Chronological ordering
  - Pagination support
  - Include deleted replies option
  - Full threading support

#### 10. **replies.update**
- **Method**: `PATCH` (v3) / `PUT` (v2)
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}`
- **Purpose**: Updates an existing reply
- **Features**:
  - Patch semantics for partial updates
  - Content modification
  - Author restrictions (only creator can update)
  - Cannot modify action after creation

#### 11. **replies.patch** (v2 only)
- **Method**: `PATCH`
- **Endpoint**: `/drive/v2/files/{fileId}/comments/{commentId}/replies/{replyId}`
- **Purpose**: Updates reply with patch semantics
- **Features**:
  - Bandwidth-optimized updates
  - Partial field modification
  - Legacy v2 API method

#### 12. **replies.delete**
- **Method**: `DELETE`
- **Endpoint**: `/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}`
- **Purpose**: Marks a reply as deleted
- **Features**:
  - Soft delete mechanism
  - Preserves threading structure
  - Author restrictions apply
  - Content fields removed when deleted

---

## Advanced Features

### Comment Resolution System

#### **Resolution via Action Replies**
- **Mechanism**: Comments resolved by creating replies with `action: "resolve"`
- **Resolution Reply**: 
  ```json
  {
    "content": "Marking this resolved",
    "action": "resolve"
  }
  ```
- **Reopening**: Use `action: "reopen"` to reopen resolved comments
- **Status Tracking**: `resolved` field becomes `true` when resolved
- **Content Optional**: Action replies can resolve without additional content

### Anchoring System

#### **Anchor Structure**
```json
{
  "anchor": {
    "r": "revision_id_or_head",
    "a": [
      {
        "type": "region_classifier",
        "coordinates": "specific_to_type"
      }
    ]
  }
}
```

#### **Region Classifiers**
- **Text-based**: `txt`, `line` classifiers for document text
- **Image-based**: 2D rectangle coordinates for image regions
- **Video-based**: Time duration segments
- **Custom**: Format-specific positioning data

#### **Revision Tracking**
- **Head Revision**: Use `"r": "head"` for latest version
- **Specific Revision**: Use revision ID for historical anchoring
- **Immutable Anchors**: Position relative to content cannot be guaranteed between revisions

### Content and Formatting

#### **Content Types**
- **Plain Text**: Standard text content
- **HTML Content**: Rich formatting via `htmlContent` field
- **Quoted Content**: `quotedFileContent` shows referenced text/region
  - `mimeType`: Type of quoted content
  - `value`: The actual quoted text/data

#### **Author Information**
```json
{
  "author": {
    "displayName": "User Name",
    "emailAddress": "user@example.com",
    "photoLink": "profile_photo_url",
    "me": true/false
  }
}
```

### Metadata and Timestamps

#### **Temporal Data**
- **createdTime**: RFC 3339 formatted creation timestamp
- **modifiedTime**: Last modification time (comment or any reply)
- **Automatic Updates**: System maintains timestamps automatically

#### **Status Fields**
- **deleted**: Boolean indicating soft deletion
- **resolved**: Boolean indicating resolution status (read-only)
- **kind**: Resource type identifier (`drive#comment`, `drive#reply`)

---

## API Versions and Differences

### Version 2 vs Version 3

| Feature | v2 API | v3 API |
|---------|--------|--------|
| **Update Methods** | `update` + `patch` | `update` (patch semantics) |
| **Resolution Field** | `status` (string) | `resolved` (boolean) |
| **Action Field** | `verb` | `action` |
| **Endpoint Pattern** | `/drive/v2/files/{fileId}/comments` | `/drive/v3/files/{fileId}/comments` |
| **Resource Names** | `CommentReply` | `Reply` |
| **Recommended Usage** | Legacy | Current |

### Authentication and Authorization

#### **Required OAuth Scopes**
- **Read Comments**: 
  - `https://www.googleapis.com/auth/drive.readonly`
  - `https://www.googleapis.com/auth/drive.file`
- **Write Comments**:
  - `https://www.googleapis.com/auth/drive`
  - `https://www.googleapis.com/auth/drive.file`

#### **Permission Requirements**
- **View Comments**: Reader access to file
- **Create Comments**: Commenter access to file
- **Edit/Delete Comments**: Must be comment author or file owner
- **Resolve Comments**: Any user with comment access

---

## Query Parameters and Options

### Common Parameters

#### **Field Selection**
- **Parameter**: `fields`
- **Required**: Yes (for most operations)
- **Purpose**: Specify exact fields to return
- **Example**: `fields=id,content,author,modifiedTime,resolved`

#### **Pagination**
- **pageToken**: Continue from previous page
- **pageSize**: Number of results per page
- **nextPageToken**: Token for next page (in response)

#### **Filtering**
- **includeDeleted**: Include soft-deleted comments/replies
- **startModifiedTime**: Filter by modification date (RFC 3339)

### Response Format

#### **Comment Resource Example**
```json
{
  "id": "comment_id",
  "content": "This is a comment",
  "htmlContent": "<p>This is a comment</p>",
  "anchor": "{\"r\":\"head\",\"a\":[...]}",
  "author": {
    "displayName": "John Doe",
    "emailAddress": "john@example.com",
    "me": false
  },
  "createdTime": "2024-01-15T10:30:00.000Z",
  "modifiedTime": "2024-01-15T10:30:00.000Z",
  "resolved": false,
  "deleted": false,
  "replies": [
    {
      "id": "reply_id",
      "content": "This is a reply",
      "action": "resolve",
      "author": {...},
      "createdTime": "2024-01-15T11:00:00.000Z"
    }
  ],
  "quotedFileContent": {
    "mimeType": "text/plain",
    "value": "Referenced text content"
  }
}
```

---

## File Type Support and Limitations

### Supported File Types

#### **Google Workspace Files**
- **Google Docs**: Full anchoring support
- **Google Sheets**: Comments supported (anchoring limitations)
- **Google Slides**: Full anchoring support
- **Google Drawings**: Full anchoring support

#### **Non-Google Files (Blob Files)**
- **Images**: Unanchored comments only
- **PDFs**: Unanchored comments only
- **Office Documents**: Unanchored comments only
- **Text Files**: Unanchored comments only

### Anchoring Limitations

#### **Supported Anchoring**
- Google Docs editor files with stable content
- Image files (recommended for read-only scenarios)
- Documents where position doesn't change frequently

#### **Not Supported**
- Blob files (binary files)
- Frequently changing document content
- Google Docs editor files (explicitly mentioned as not supported for anchored comments)

---

## Error Handling and Best Practices

### Common Error Scenarios

#### **Permission Errors**
- **403 Forbidden**: Insufficient permissions to access/modify comments
- **Author Mismatch**: Only comment/reply creators can edit/delete
- **File Access**: User must have at least read access to file

#### **Resource Not Found**
- **404 Error**: Comment/reply ID doesn't exist or was deleted
- **File Not Found**: Invalid file ID in request

#### **Validation Errors**
- **400 Bad Request**: Invalid anchor format or missing required fields
- **Invalid Action**: Unsupported action type in replies

### Best Practices

#### **Performance Optimization**
- **Use Patch**: Prefer `PATCH` over `PUT` for updates
- **Field Selection**: Always specify `fields` parameter
- **Pagination**: Handle large result sets with page tokens
- **Batch Operations**: Group related operations when possible

#### **User Experience**
- **Revision Awareness**: Clearly indicate which revision comments belong to
- **Resolution Status**: Show resolved comments differently in UI
- **Author Permissions**: Check `author.me` field before allowing edit/delete
- **Deleted Comments**: Handle soft-deleted comments gracefully

#### **Data Integrity**
- **Anchor Validation**: Verify anchor format before creation
- **Content Sanitization**: Sanitize HTML content for security
- **Error Recovery**: Implement retry logic for transient failures
- **Quota Management**: Monitor API usage limits

---

## Implementation Considerations for MCP Servers

### Required Capabilities for Full Comment Support

#### **Core Operations (12 methods)**
1. Create comment (anchored/unanchored)
2. Get comment by ID
3. List all comments on file
4. Update comment content
5. Delete comment
6. Create reply to comment
7. Get reply by ID
8. List replies to comment
9. Update reply content
10. Delete reply
11. Resolve comment via action reply
12. Reopen resolved comment

#### **Advanced Features**
- **Anchoring System**: JSON anchor parsing and validation
- **Resolution Management**: Action-based comment resolution
- **Threading Support**: Hierarchical comment/reply structure
- **Author Permissions**: Edit/delete permission validation
- **Content Processing**: HTML/plain text handling
- **Pagination**: Large result set handling

#### **Integration Requirements**
- **Dual API Access**: Both Drive API and Sheets API (for sheets)
- **OAuth Scope Management**: Appropriate permission levels
- **Error Handling**: Comprehensive error recovery
- **Rate Limiting**: API quota management
- **Field Selection**: Efficient data retrieval

### Technical Complexity Assessment

#### **Low Complexity**
- Basic CRUD operations (create, read, update, delete)
- Unanchored comments on any file type
- Simple reply threading

#### **Medium Complexity**
- Comment resolution via action replies
- Author permission validation
- Pagination and filtering
- HTML content handling

#### **High Complexity**
- Anchored comment system with region classifiers
- Revision-aware anchoring
- Cross-API integration (Drive + Sheets)
- Advanced error handling and recovery

---

## Common Use Cases and Required Operations

### Basic Comment Listing Operations

#### **Use Case 1: List All Comments (Open + Resolved)**
**API Operations Required:**
1. `comments.list` with `fields=*` 
2. Optional: `replies.list` for each comment (if full threading needed)

**Parameters:**
- `includeDeleted=false` (exclude deleted comments)
- No resolution filtering (returns both open and resolved)

**Implementation Notes:**
- Single API call retrieves all comment states
- `resolved` field indicates status for each comment
- Replies included in comment response by default

---

#### **Use Case 2: List Only Open Comments**
**API Operations Required:**
1. `comments.list` with `fields=*`
2. **Client-side filtering** by `resolved=false`

**Implementation Notes:**
- API doesn't support server-side resolution filtering
- Must retrieve all comments and filter locally
- Consider caching for performance

---

#### **Use Case 3: List Only Resolved Comments**
**API Operations Required:**
1. `comments.list` with `fields=*`
2. **Client-side filtering** by `resolved=true`

**Implementation Notes:**
- Same limitation as Use Case 2
- Filter resolved comments on client side
- May want to paginate due to potentially large resolved comment sets

---

### Google Sheets Spatial Filtering

#### **Use Case 4: Filter Comments by Row**
**API Operations Required:**
1. `comments.list` with full anchor data
2. **Client-side anchor parsing** to extract row information
3. Filter comments where anchor matches target row

**Anchor Analysis Required:**
```json
{
  "anchor": {
    "r": "head",
    "a": [
      {
        "type": "range_classifier", 
        "startRow": N,
        "endRow": N
      }
    ]
  }
}
```

**Implementation Complexity:** HIGH - Requires anchor JSON parsing

---

#### **Use Case 5: Filter Comments by Column**
**API Operations Required:**
1. `comments.list` with full anchor data
2. **Client-side anchor parsing** to extract column information
3. Filter comments where anchor matches target column

**Anchor Analysis Required:**
```json
{
  "anchor": {
    "r": "head", 
    "a": [
      {
        "type": "range_classifier",
        "startColumn": N,
        "endColumn": N
      }
    ]
  }
}
```

---

#### **Use Case 6: Filter Comments by Specific Cell**
**API Operations Required:**
1. `comments.list` with full anchor data
2. **Client-side anchor parsing** for exact cell match
3. Filter comments where anchor matches specific cell coordinates

**Anchor Analysis Required:**
```json
{
  "anchor": {
    "r": "head",
    "a": [
      {
        "type": "cell_classifier",
        "row": N,
        "column": N
      }
    ]
  }
}
```

**Note:** Exact anchor format for Sheets cells requires reverse engineering from actual API responses.

---

### Comment Attribution

#### **Use Case 7: Get Comment Attribution Data**
**Attribution Included by Default:** ✅ **YES**

**API Operations Required:**
1. `comments.get` or `comments.list` 
2. Attribution automatically included in response

**Default Attribution Data:**
```json
{
  "author": {
    "displayName": "John Doe",
    "emailAddress": "john@example.com", 
    "photoLink": "https://profile-photo-url",
    "me": false
  },
  "createdTime": "2024-01-15T10:30:00.000Z",
  "modifiedTime": "2024-01-15T11:00:00.000Z"
}
```

**Available Attribution Fields:**
- **displayName**: User's display name
- **emailAddress**: User's email address  
- **photoLink**: Profile photo URL
- **me**: Boolean indicating if current user is the author
- **createdTime**: When comment was created
- **modifiedTime**: When comment was last modified

---

### Comment Creation Operations

#### **Use Case 8: Add Comment to Specific Cell**
**API Operations Required:**
1. `comments.create` with cell-specific anchor

**Required Parameters:**
```json
{
  "content": "Comment text",
  "anchor": {
    "r": "head",
    "a": [
      {
        "type": "cell_range",
        "startRow": N,
        "startColumn": N,
        "endRow": N,
        "endColumn": N
      }
    ]
  }
}
```

**Implementation Notes:**
- Anchor format may need experimentation/documentation review
- Consider unanchored comments as fallback

---

#### **Use Case 9: Add Comment to Cell Range/Row/Column**
**API Operations Required:**
1. `comments.create` with range-specific anchor

**Range Anchor Examples:**
```json
// Full Row
{
  "anchor": {
    "r": "head",
    "a": [{"type": "row", "row": N}]
  }
}

// Full Column  
{
  "anchor": {
    "r": "head",
    "a": [{"type": "column", "column": N}]
  }
}

// Cell Range
{
  "anchor": {
    "r": "head", 
    "a": [{"type": "range", "startRow": N1, "endRow": N2, "startColumn": M1, "endColumn": M2}]
  }
}
```

---

### Comment Interaction Operations

#### **Use Case 10: Reply to Specific Comment**
**API Operations Required:**
1. `replies.create` with `commentId`

**Required Parameters:**
```json
{
  "content": "Reply text"
}
```

**Optional Action Parameter:**
```json
{
  "content": "Reply text",
  "action": "resolve" // or "reopen"
}
```

---

#### **Use Case 11: Mark Comment as Resolved**
**API Operations Required:**
1. `replies.create` with resolve action

**Required Parameters:**
```json
{
  "action": "resolve",
  "content": "Marking as resolved" // optional
}
```

**Implementation Notes:**
- Cannot directly update comment resolution status
- Must create action reply to resolve
- Comment `resolved` field becomes `true` automatically

---

#### **Use Case 12: Mark Resolved Comment as Unresolved**
**API Operations Required:**
1. `replies.create` with reopen action

**Required Parameters:**
```json
{
  "action": "reopen", 
  "content": "Reopening this issue" // optional
}
```

**Implementation Notes:**
- Creates new reply with reopen action
- Comment `resolved` field becomes `false`
- Previous resolution replies remain in thread

---

#### **Use Case 13: Delete Comments (Remove Spam)**
**API Operations Required:**
1. `comments.delete` with `commentId`

**Authorization Requirements:**
- Must be comment author OR file owner
- Check `author.me` field before allowing deletion

**Implementation Notes:**
- Soft delete (comment marked as `deleted: true`)
- Content fields removed but structure preserved
- Cannot be undone via API

---

### @Mention Detection and Implementation

#### **Use Case 14: Detect @Username Mentions in Comments**

**Detection in Existing Comments:**
- **API Support**: ❌ **NO BUILT-IN PARSING**
- **Implementation**: Manual text parsing required
- **Pattern**: Look for `@email@domain.com` or `@DisplayName` patterns

**Manual Detection Logic:**
```javascript
function extractMentions(commentContent) {
  // Email pattern: @user@domain.com
  const emailMentions = commentContent.match(/@[\w\.-]+@[\w\.-]+\.\w+/g);
  
  // Display name pattern: @FirstName LastName  
  const nameMentions = commentContent.match(/@[\w\s]+(?=\s|$)/g);
  
  return {
    emails: emailMentions || [],
    names: nameMentions || []
  };
}
```

---

#### **Use Case 15: Create Comments with @Mentions**

**Current Limitation:** ❌ **NO NATIVE @MENTION API**

**Workaround Implementation:**
1. `comments.create` with manual mention formatting
2. Separate notification system required

**Manual Mention Format:**
```json
{
  "content": "Hey @john@company.com, please review this data",
  "htmlContent": "Hey <span class='mention'>@john@company.com</span>, please review this data"
}
```

**Required Additional Implementation:**
- **Email Detection**: Parse comment for email addresses
- **User Validation**: Verify mentioned users have file access
- **Notification System**: Send custom notifications (Drive API doesn't auto-notify)
- **Permission Check**: Ensure mentioned users can access the file

**Notification Workflow:**
1. Create comment with @mention text
2. Extract email addresses from comment content
3. Check file permissions for mentioned users
4. Send custom email/notification to mentioned users
5. Include link to comment location

---

### Advanced Filtering and Search Operations

#### **Use Case 16: Search Comments by Content**
**API Operations Required:**
1. `comments.list` to retrieve all comments
2. **Client-side text search** through content fields

**Search Fields:**
- `content` (plain text)
- `htmlContent` (formatted content)
- `quotedFileContent.value` (referenced content)

**Implementation Notes:**
- No server-side content search available
- Must implement local search/indexing
- Consider fuzzy matching for better UX

---

#### **Use Case 17: Filter Comments by Date Range**
**API Operations Required:**
1. `comments.list` with `startModifiedTime` parameter
2. Client-side filtering for end date

**Parameters:**
```
startModifiedTime: "2024-01-01T00:00:00.000Z"
```

**Implementation Notes:**
- API only supports start date filtering
- End date filtering must be done client-side
- Use `modifiedTime` field for filtering

---

#### **Use Case 18: Filter Comments by Author**
**API Operations Required:**
1. `comments.list` to retrieve all comments  
2. **Client-side filtering** by author email/name

**Filter Options:**
```javascript
function filterByAuthor(comments, authorEmail) {
  return comments.filter(comment => 
    comment.author.emailAddress === authorEmail
  );
}

function filterByDisplayName(comments, displayName) {
  return comments.filter(comment => 
    comment.author.displayName === displayName
  );
}
```

---

## **MCP Server Architecture & Integration**

### **Separation of Concerns Design**

This comment-focused MCP server is designed to work **alongside** other specialized MCP servers:

#### **Division of Responsibilities**
- **📊 Sheets/Docs MCP Server**: Handles reading/writing actual spreadsheet data and document content
- **💬 Comments MCP Server** (this specification): Handles all comment-related operations exclusively
- **🔄 Workflow Integration**: Both servers work together via shared spreadsheet IDs

#### **Integration Pattern**
```
AI Agent
    ├── 📊 Sheets MCP Server → Read cell B5 value: "Draft Complete"
    └── 💬 Comments MCP Server → Get comments for cell B5: [volunteer feedback]
```

#### **Workflow Management Strategy**
**Tracking via Separate Spreadsheet**: 
- Maintain volunteer assignments and progress in dedicated tracking sheet
- Update workflow status through Sheets MCP Server
- Use Comments MCP Server to review feedback on work products
- Cross-reference between tracking sheet and commented documents

**Example Workflow Integration**:
```
1. Sheets MCP: Check tracking sheet → "John assigned rows 15-25, status: Complete"
2. Comments MCP: Get comments for rows 15-25 → [analyst review needed]
3. AI: Analyze John's work + comments → Provide review summary
4. Sheets MCP: Update tracking sheet → "John: Reviewed, approved"
5. Comments MCP: Mark comments resolved → Close feedback loop
```

### **Benefits of This Architecture**
- **🎯 Focused Functionality**: Each server optimized for its specific domain
- **🔧 Maintainability**: Easier to update/debug specialized servers
- **⚡ Performance**: No API scope conflicts or authentication complexity
- **🔄 Reusability**: Comment server works with any Google Drive file type

---

## **CRITICAL FEATURE: Intelligent Comment Caching System**

### **Two-Mode Operation Architecture**

#### **Mode 1: Initial Load (Fresh Fetch)**
```
User Request → MCP Server → Google Drive API → Full Comment List
                     ↓
Cache in Memory with Timestamp + Build Spatial Index
                     ↓
Return Filtered Results to AI
```

#### **Mode 2: Cached Access (Subsequent Requests)**  
```
User Request → MCP Server → Check Cache → Return Filtered Results
                     ↓
            No API Call Required
```

### **Cache Management Strategy**

#### **Cache Storage Structure**
```json
{
  "spreadsheetId": "abc123",
  "lastFetched": "2024-01-15T14:30:00.000Z",
  "comments": [...], // Full comment list
  "spatialIndex": {
    "A1": [commentId1, commentId2],
    "B1": [commentId3],
    "row_1": [commentId1, commentId2, commentId3],
    "col_A": [commentId1, commentId4]
  },
  "totalComments": 1247,
  "resolvedCount": 892,
  "openCount": 355
}
```

#### **Cache Invalidation Triggers (CRITICAL SAFETY)**

**Automatic Invalidation:**
- ✅ **Comment Creation** → Cache invalidated, fresh fetch required
- ✅ **Reply Creation** → Cache invalidated (changes comment.modifiedTime)
- ✅ **Comment Update/Edit** → Cache invalidated
- ✅ **Comment Deletion** → Cache invalidated  
- ✅ **Comment Resolution** (via reply) → Cache invalidated
- ✅ **Comment Reopening** → Cache invalidated

**Manual Invalidation:**
- ✅ **User requests refresh** → `refresh_comments` MCP tool
- ✅ **Explicit cache clear** → `clear_comment_cache` MCP tool

#### **Implementation Safety Measures**

**Write-Through Pattern:**
```javascript
async function createComment(spreadsheetId, commentData) {
  // 1. Perform write operation
  const newComment = await driveAPI.comments.create(commentData);
  
  // 2. Immediately invalidate cache
  commentCache.delete(spreadsheetId);
  
  // 3. Return result (next read will fresh-fetch)
  return newComment;
}
```

**Cache Staleness Prevention:**
```javascript
// Add timestamp check for extra safety
async function getComments(spreadsheetId, filterOptions) {
  const cached = commentCache.get(spreadsheetId);
  
  // Force refresh if cache is older than 1 hour (safety net)
  const MAX_CACHE_AGE = 60 * 60 * 1000; // 1 hour
  const cacheAge = Date.now() - new Date(cached?.lastFetched).getTime();
  
  if (!cached || cacheAge > MAX_CACHE_AGE) {
    return await fetchFreshComments(spreadsheetId);
  }
  
  return filterCachedComments(cached, filterOptions);
}
```

### **MCP Tools for Cache Management**

#### **Smart Comment Retrieval**
```json
// Automatically uses cache when safe
{
  "name": "get_comments_for_cell",
  "parameters": {
    "spreadsheetId": "abc123",
    "cell": "A5",
    "forceRefresh": false  // Optional override
  }
}
```

#### **Explicit Cache Control**
```json
// Force fresh fetch
{
  "name": "refresh_comments",
  "parameters": {
    "spreadsheetId": "abc123"
  }
}

// Clear cache without fetching
{
  "name": "clear_comment_cache", 
  "parameters": {
    "spreadsheetId": "abc123"
  }
}

// Get cache status
{
  "name": "get_cache_info",
  "parameters": {
    "spreadsheetId": "abc123"
  }
}
```

### **Performance Benefits**

#### **Dramatic Speed Improvement**
- **First Request**: ~2-5 seconds (API fetch + processing)
- **Subsequent Requests**: ~50-100ms (cache lookup + filtering)
- **50x+ performance improvement** for cached operations

#### **Reduced API Usage**
- **Without Cache**: Every comment request = API call
- **With Cache**: One API call serves dozens of filtered requests
- **Stays within API rate limits** even with heavy usage

#### **Context Window Efficiency**
- **Spatial filtering** works instantly on cached data
- **No repeated large API responses** cluttering logs
- **Consistent response times** for AI interactions

### **User Experience Flow**

#### **Typical Session**
```
1. User: "Show me comments on cell B5"
   → MCP: Fresh fetch + cache + return B5 comments

2. User: "What about row 5?"  
   → MCP: Use cache + return row 5 comments (instant)

3. User: "Show column B comments"
   → MCP: Use cache + return column B comments (instant)

4. User: "Add a comment to B6"
   → MCP: Create comment + invalidate cache

5. User: "Show me B5 comments again"
   → MCP: Fresh fetch (cache was invalidated) + return B5 comments
```

#### **Explicit Refresh Scenarios**
```
User: "Refresh the comments list"
→ MCP: Force fresh fetch + rebuild cache + return status

User: "Someone else might have added comments, can you check?"
→ MCP: Fresh fetch + compare with cache + report changes
```

### **Safety Considerations**

#### **Write Operation Safety** ✅
- Every write immediately invalidates cache
- No risk of stale data after modifications
- Next read guaranteed to be fresh

#### **Collaborative Safety** ⚠️
- **Known Limitation**: External changes by other users not detected
- **Mitigation**: Manual refresh capability available
- **Trade-off**: Performance vs. real-time accuracy

#### **Memory Management** ✅
- Cache size limits per spreadsheet
- LRU eviction for oldest cached spreadsheets
- Configurable memory usage limits

#### **Error Handling** ✅
```javascript
// If cache is corrupted, fall back to fresh fetch
async function getCommentsWithFallback(spreadsheetId, options) {
  try {
    return await getCachedComments(spreadsheetId, options);
  } catch (cacheError) {
    console.warn('Cache error, falling back to fresh fetch:', cacheError);
    commentCache.delete(spreadsheetId);
    return await fetchFreshComments(spreadsheetId);
  }
}
```

---

## **CRITICAL FEATURE: Context Management for AI Interactions**

### **The Scalability Challenge**
Many production Google Sheets contain **hundreds or thousands of comments**, which creates severe problems:

- **Context Overflow**: Sending all comments to AI will exceed context limits
- **Irrelevant Noise**: Most comments are unrelated to current work focus
- **Performance Degradation**: Processing massive comment sets slows interactions
- **Cost Implications**: Large context usage increases AI API costs

### **Required MCP Server Intelligence**

The MCP server **MUST** implement smart filtering to provide only relevant comments to AI:

#### **Spatial Context Filtering (CRITICAL)**
```json
// MCP Tool: get_comments_for_cell
{
  "name": "get_comments_for_cell", 
  "parameters": {
    "spreadsheetId": "abc123",
    "cell": "A5"
  }
}
// Returns: Only comments anchored to cell A5

// MCP Tool: get_comments_for_row
{
  "name": "get_comments_for_row",
  "parameters": {
    "spreadsheetId": "abc123", 
    "row": 5
  }
}
// Returns: Only comments anchored to any cell in row 5

// MCP Tool: get_comments_for_column  
{
  "name": "get_comments_for_column",
  "parameters": {
    "spreadsheetId": "abc123",
    "column": "A"
  }
}
// Returns: Only comments anchored to any cell in column A
```

#### **Implementation Architecture**
```
1. MCP Server fetches ALL comments (background process)
2. Parses anchor data to build spatial index:
   {
     "A1": [comment1, comment2],
     "B1": [comment3], 
     "A2": [comment4],
     "row_1": [comment1, comment2, comment3],
     "col_A": [comment1, comment4]
   }
3. AI requests only relevant subset via MCP tools
4. Server returns filtered comments matching spatial criteria
```

#### **Context Management Benefits**
- **Focused Conversations**: AI only sees comments related to current work
- **Context Efficiency**: Dramatically reduced token usage
- **Improved Relevance**: AI responses more targeted to specific data
- **Scalable Performance**: Works with documents containing thousands of comments

---

## Implementation Priority Matrix

### **CRITICAL (Must Have for Production)**
1. 🔥 **Spatial context filtering** (Use Cases 4-6) - **PROMOTED TO CRITICAL**
2. 🔥 **Comment cache management** with anchor parsing
3. ✅ List all comments (Use Cases 1-3)
4. ✅ Get comment attribution (Use Case 7) 
5. ✅ Add comments to cells/ranges (Use Cases 8-9)
6. ✅ Reply to comments (Use Case 10)
7. ✅ Resolve/unresolve comments (Use Cases 11-12)
8. ✅ Delete comments (Use Case 13)

### **High Priority (Enhanced UX)**
9. 🔶 Search comments by content (Use Case 16)
10. 🔶 Filter by date range (Use Case 17)
11. 🔶 Filter by author (Use Case 18)

### **Medium Priority (Advanced Features)**
12. 🔻 @Mention detection (Use Case 14)
13. 🔻 @Mention creation with notifications (Use Case 15)

---

## Technical Implementation Notes

### **Client-Side Processing Required**
- Resolution status filtering (no server-side support)
- Spatial filtering for Sheets (anchor parsing required)
- Content search (no server-side search API)
- Date range end filtering
- Author filtering
- @Mention detection

### **API Limitations to Address**
- **No server-side filtering** for most criteria
- **No native @mention support** 
- **Anchor format documentation** may require reverse engineering
- **No bulk operations** for mass comment management

### **Performance Considerations**
- **Caching Strategy**: Cache comment lists for repeated filtering
- **Pagination**: Handle large comment sets efficiently  
- **Lazy Loading**: Load replies on-demand
- **Index Building**: Consider local indexing for search functionality

---

*This comprehensive use case mapping provides the foundation for implementing a full-featured comment management system in an MCP server, with clear API operation requirements and implementation complexity assessments.*

