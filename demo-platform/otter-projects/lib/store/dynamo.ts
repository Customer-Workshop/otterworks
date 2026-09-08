import { ConditionalCheckFailedException, DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  BatchWriteCommand,
  DeleteCommand,
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  QueryCommand,
  ScanCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import type { ActivityEvent, Comment, Project, Ticket, WebhookDelivery } from "@/lib/types";
import { padNumber, projectKeyOf, ticketNumberOf, type Store } from "./types";

type Item = Record<string, unknown>;

/** Single-table DynamoDB store; see ./types.ts for the key layout. */
export class DynamoStore implements Store {
  private readonly doc: DynamoDBDocumentClient;

  constructor(
    private readonly table: string,
    region: string,
  ) {
    this.doc = DynamoDBDocumentClient.from(new DynamoDBClient({ region }), {
      marshallOptions: { removeUndefinedValues: true },
    });
  }

  private async query(pk: string, skPrefix: string): Promise<Item[]> {
    const out: Item[] = [];
    let start: Record<string, unknown> | undefined;
    do {
      const res = await this.doc.send(
        new QueryCommand({
          TableName: this.table,
          KeyConditionExpression: "PK = :pk AND begins_with(SK, :sk)",
          ExpressionAttributeValues: { ":pk": pk, ":sk": skPrefix },
          ExclusiveStartKey: start,
        }),
      );
      out.push(...((res.Items ?? []) as Item[]));
      start = res.LastEvaluatedKey;
    } while (start);
    return out;
  }

  private async put(pk: string, sk: string, data: object): Promise<void> {
    await this.doc.send(new PutCommand({ TableName: this.table, Item: { ...(data as Item), PK: pk, SK: sk } }));
  }

  private strip<T>(item: Item): T {
    const { PK: _pk, SK: _sk, ...rest } = item;
    return rest as T;
  }

  async listProjects(): Promise<Project[]> {
    const out: Project[] = [];
    let start: Record<string, unknown> | undefined;
    do {
      const res = await this.doc.send(
        new ScanCommand({
          TableName: this.table,
          FilterExpression: "SK = :meta",
          ExpressionAttributeValues: { ":meta": "META" },
          ExclusiveStartKey: start,
        }),
      );
      out.push(...((res.Items ?? []) as Item[]).map((i) => this.strip<Project>(i)));
      start = res.LastEvaluatedKey;
    } while (start);
    return out.sort((a, b) => a.key.localeCompare(b.key));
  }
  async getProject(key: string): Promise<Project | null> {
    const res = await this.doc.send(new GetCommand({ TableName: this.table, Key: { PK: `PROJECT#${key}`, SK: "META" } }));
    return res.Item ? this.strip<Project>(res.Item) : null;
  }
  async putProject(project: Project): Promise<void> {
    await this.put(`PROJECT#${project.key}`, "META", project);
  }
  async createProject(project: Project): Promise<boolean> {
    try {
      await this.doc.send(
        new PutCommand({
          TableName: this.table,
          Item: { ...(project as unknown as Item), PK: `PROJECT#${project.key}`, SK: "META" },
          ConditionExpression: "attribute_not_exists(PK)",
        }),
      );
      return true;
    } catch (err) {
      if (err instanceof ConditionalCheckFailedException) return false;
      throw err;
    }
  }
  async deleteProject(key: string): Promise<void> {
    for (const t of await this.listTickets(key)) await this.deleteTicket(t);
    await this.batchDelete(`PROJECT#${key}`, ["META", "COUNTER"]);
  }

  async nextTicketNumber(projectKey: string): Promise<number> {
    const res = await this.doc.send(
      new UpdateCommand({
        TableName: this.table,
        Key: { PK: `PROJECT#${projectKey}`, SK: "COUNTER" },
        UpdateExpression: "ADD n :one",
        ExpressionAttributeValues: { ":one": 1 },
        ReturnValues: "UPDATED_NEW",
      }),
    );
    return Number(res.Attributes?.n ?? 1);
  }
  async listTickets(projectKey: string): Promise<Ticket[]> {
    return (await this.query(`PROJECT#${projectKey}`, "TICKET#")).map((i) => this.strip<Ticket>(i));
  }
  async listTicketsWithSessions(): Promise<Ticket[]> {
    const out: Ticket[] = [];
    let start: Record<string, unknown> | undefined;
    do {
      const res = await this.doc.send(
        new ScanCommand({
          TableName: this.table,
          FilterExpression: "begins_with(SK, :t) AND attribute_exists(devin.sessionId)",
          ExpressionAttributeValues: { ":t": "TICKET#" },
          ExclusiveStartKey: start,
        }),
      );
      out.push(...((res.Items ?? []) as Item[]).map((i) => this.strip<Ticket>(i)));
      start = res.LastEvaluatedKey;
    } while (start);
    return out;
  }
  async getTicket(key: string): Promise<Ticket | null> {
    const pk = projectKeyOf(key);
    const n = ticketNumberOf(key);
    if (!pk || n === null) return null;
    const res = await this.doc.send(
      new GetCommand({ TableName: this.table, Key: { PK: `PROJECT#${pk}`, SK: `TICKET#${padNumber(n)}` } }),
    );
    return res.Item ? this.strip<Ticket>(res.Item) : null;
  }
  async putTicket(ticket: Ticket): Promise<void> {
    await this.put(`PROJECT#${ticket.projectKey}`, `TICKET#${padNumber(ticket.number)}`, ticket);
  }
  async claimDispatch(ticketKey: string, at: number): Promise<boolean> {
    const pk = projectKeyOf(ticketKey);
    const n = ticketNumberOf(ticketKey);
    if (!pk || n === null) return false;
    try {
      await this.doc.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { PK: `PROJECT#${pk}`, SK: `TICKET#${padNumber(n)}` },
          UpdateExpression: "SET devin.dispatchedAt = :at",
          ConditionExpression:
            "attribute_exists(PK) AND attribute_not_exists(devin.sessionId) AND attribute_not_exists(devin.dispatchedAt)",
          ExpressionAttributeValues: { ":at": at },
        }),
      );
      return true;
    } catch (err) {
      if (err instanceof ConditionalCheckFailedException) return false;
      throw err;
    }
  }
  async deleteTicket(ticket: Ticket): Promise<void> {
    const children = await this.query(`TICKET#${ticket.key}`, "");
    await this.batchDelete(
      `TICKET#${ticket.key}`,
      children.map((c) => String(c.SK)),
    );
    await this.doc.send(
      new DeleteCommand({
        TableName: this.table,
        Key: { PK: `PROJECT#${ticket.projectKey}`, SK: `TICKET#${padNumber(ticket.number)}` },
      }),
    );
  }

  async listComments(ticketKey: string): Promise<Comment[]> {
    return (await this.query(`TICKET#${ticketKey}`, "COMMENT#")).map((i) => this.strip<Comment>(i));
  }
  async addComment(comment: Comment): Promise<void> {
    await this.put(`TICKET#${comment.ticketKey}`, `COMMENT#${comment.createdAt}#${comment.id}`, comment);
  }

  async listEvents(ticketKey: string): Promise<ActivityEvent[]> {
    return (await this.query(`TICKET#${ticketKey}`, "EVENT#")).map((i) => this.strip<ActivityEvent>(i));
  }
  async addEvent(event: ActivityEvent): Promise<void> {
    await this.put(`TICKET#${event.ticketKey}`, `EVENT#${event.createdAt}#${event.id}`, event);
  }

  async listDeliveries(ticketKey: string): Promise<WebhookDelivery[]> {
    return (await this.query(`TICKET#${ticketKey}`, "WEBHOOK#")).map((i) => this.strip<WebhookDelivery>(i));
  }
  async addDelivery(delivery: WebhookDelivery): Promise<void> {
    await this.put(`TICKET#${delivery.ticketKey}`, `WEBHOOK#${delivery.createdAt}#${delivery.id}`, delivery);
  }

  private async batchDelete(pk: string, sks: string[]): Promise<void> {
    for (let i = 0; i < sks.length; i += 25) {
      let requests: Record<string, { DeleteRequest?: { Key: Item } }[]> = {
        [this.table]: sks.slice(i, i + 25).map((sk) => ({ DeleteRequest: { Key: { PK: pk, SK: sk } } })),
      };
      for (let attempt = 0; ; attempt += 1) {
        const res = await this.doc.send(new BatchWriteCommand({ RequestItems: requests }));
        const unprocessed = res.UnprocessedItems ?? {};
        if (!Object.values(unprocessed).some((v) => v && v.length > 0)) break;
        if (attempt >= 5) throw new Error(`DynamoDB left ${Object.values(unprocessed).flat().length} deletes unprocessed for ${pk}`);
        await new Promise((r) => setTimeout(r, 50 * 2 ** attempt));
        requests = unprocessed as typeof requests;
      }
    }
  }
}
