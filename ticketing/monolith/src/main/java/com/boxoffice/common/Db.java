package com.boxoffice.common;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

/**
 * The one JDBC helper every module in the application goes through.
 * Connections come from the container-managed datasource and enlist in the
 * caller's JTA transaction, so a purchase is one transaction end to end.
 */
public final class Db {

    public static final String JNDI = "java:jboss/datasources/BoxOfficeDS";

    private static volatile DataSource dataSource;

    private Db() {
    }

    public static DataSource ds() {
        if (dataSource == null) {
            synchronized (Db.class) {
                if (dataSource == null) {
                    try {
                        dataSource = (DataSource) new InitialContext().lookup(JNDI);
                    } catch (NamingException e) {
                        throw new BoxOfficeException("datasource " + JNDI + " not bound", e);
                    }
                }
            }
        }
        return dataSource;
    }

    public static List<Map<String, Object>> query(String sql, Object... args) {
        try (Connection c = ds().getConnection(); PreparedStatement ps = prepare(c, sql, args);
             ResultSet rs = ps.executeQuery()) {
            return rows(rs);
        } catch (SQLException e) {
            throw new BoxOfficeException("query failed: " + sql, e);
        }
    }

    public static Map<String, Object> one(String sql, Object... args) {
        List<Map<String, Object>> r = query(sql, args);
        return r.isEmpty() ? null : r.get(0);
    }

    public static long scalarLong(String sql, Object... args) {
        Map<String, Object> row = one(sql, args);
        if (row == null) {
            return 0L;
        }
        Object v = row.values().iterator().next();
        return v == null ? 0L : ((Number) v).longValue();
    }

    public static int update(String sql, Object... args) {
        try (Connection c = ds().getConnection(); PreparedStatement ps = prepare(c, sql, args)) {
            return ps.executeUpdate();
        } catch (SQLException e) {
            throw new BoxOfficeException("update failed: " + sql, e);
        }
    }

    public static long insert(String sql, Object... args) {
        try (Connection c = ds().getConnection();
             PreparedStatement ps = c.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            bind(ps, args);
            ps.executeUpdate();
            try (ResultSet keys = ps.getGeneratedKeys()) {
                keys.next();
                return keys.getLong(1);
            }
        } catch (SQLException e) {
            throw new BoxOfficeException("insert failed: " + sql, e);
        }
    }

    public static Timestamp now() {
        return new Timestamp(System.currentTimeMillis());
    }

    private static PreparedStatement prepare(Connection c, String sql, Object... args) throws SQLException {
        PreparedStatement ps = c.prepareStatement(sql);
        bind(ps, args);
        return ps;
    }

    private static void bind(PreparedStatement ps, Object... args) throws SQLException {
        for (int i = 0; i < args.length; i++) {
            ps.setObject(i + 1, args[i]);
        }
    }

    private static List<Map<String, Object>> rows(ResultSet rs) throws SQLException {
        List<Map<String, Object>> out = new ArrayList<>();
        ResultSetMetaData md = rs.getMetaData();
        while (rs.next()) {
            Map<String, Object> row = new LinkedHashMap<>();
            for (int i = 1; i <= md.getColumnCount(); i++) {
                row.put(md.getColumnLabel(i), rs.getObject(i));
            }
            out.add(row);
        }
        return out;
    }
}
